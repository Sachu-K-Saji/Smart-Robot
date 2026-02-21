"""
Campus Guide Robot - Main Entry Point
State machine controller coordinating all subsystems.
"""
import logging
import signal
import sys
import threading
import time

from statemachine import StateMachine, State

from config import (
    DB_PATH, CAMPUS_MAP_PATH, WAKE_WORD, FUZZY_THRESHOLD,
)
from modules.database import CampusDatabase
from modules.navigator import CampusNavigator
from modules.intent_parser import IntentParser, ParsedIntent
from modules.speech_recognition import SpeechRecognizer
from modules.text_to_speech import TextToSpeech
from modules.eye_display import EyeDisplay, Expression
from modules.video_player import VideoPlayer
from modules.power_monitor import PowerMonitor

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")


# ══════════════════════════════════════════════════════════════
#  State Machine Definition
# ══════════════════════════════════════════════════════════════

class RobotStateMachine(StateMachine):
    """
    Campus robot state machine.
    States: idle -> listening -> processing -> responding -> idle
    """

    idle = State(initial=True)
    listening = State()
    processing = State()
    responding = State()

    wake_up = idle.to(listening)
    hear_input = listening.to(processing)
    generate_response = processing.to(responding)
    finish_response = responding.to(idle)
    timeout = listening.to(idle)
    error = (
        listening.to(idle)
        | processing.to(idle)
        | responding.to(idle)
    )

    def __init__(self, robot: "CampusRobot"):
        self.robot = robot
        super().__init__()

    def on_enter_idle(self):
        logger.info("STATE: idle")
        self.robot.eye_display.expression = Expression.IDLE

    def on_enter_listening(self):
        logger.info("STATE: listening")
        self.robot.eye_display.expression = Expression.LISTENING

    def on_enter_processing(self):
        logger.info("STATE: processing")
        self.robot.eye_display.expression = Expression.THINKING

    def on_enter_responding(self):
        logger.info("STATE: responding")
        self.robot.eye_display.expression = Expression.SPEAKING


# ══════════════════════════════════════════════════════════════
#  Main Robot Controller
# ══════════════════════════════════════════════════════════════

class CampusRobot:
    """
    Orchestrates all subsystems: STT, TTS, display, navigation,
    database, video player, and power monitor.
    """

    def __init__(self):
        logger.info("Initializing Campus Guide Robot...")

        self._is_speaking_event = threading.Event()
        self._shutdown_event = threading.Event()

        # Initialize subsystems
        self.database = CampusDatabase(DB_PATH)
        self.navigator = CampusNavigator(CAMPUS_MAP_PATH)
        self.intent_parser = IntentParser(
            location_names=self.database.get_all_location_names(),
            faculty_names=self.database.get_all_faculty_names(),
            department_names=self.database.get_all_department_names(),
            fuzzy_threshold=FUZZY_THRESHOLD,
        )

        self.speech_recognizer = SpeechRecognizer()
        self.speech_recognizer._is_speaking = self._is_speaking_event

        self.tts = TextToSpeech(self._is_speaking_event)
        self.eye_display = EyeDisplay()
        self.video_player = VideoPlayer()
        self.power_monitor = PowerMonitor(
            on_low_battery=self._on_low_battery,
            on_critical_battery=self._on_critical_battery,
        )

        self.state_machine = RobotStateMachine(self)

        logger.info("All subsystems initialized.")

    def start(self):
        """Start all subsystem threads and enter the main loop."""
        logger.info("Starting subsystems...")
        self.eye_display.start()
        self.speech_recognizer.start()
        self.power_monitor.start()

        self.tts.speak(
            "Hello! I am your campus guide robot. "
            "Say 'hey robot' followed by your question to get started."
        )

        self._main_loop()

    def _main_loop(self):
        """Main event loop. Reads from speech recognizer and drives state machine."""
        logger.info("Entering main loop...")

        while not self._shutdown_event.is_set():
            try:
                if self.state_machine.current_state == self.state_machine.idle:
                    text = self.speech_recognizer.get_result(timeout=1.0)
                    if text is None:
                        continue
                    if WAKE_WORD in text.lower():
                        self.state_machine.wake_up()
                        self.tts.speak("I'm listening. How can I help you?")
                        remainder = text.lower().replace(WAKE_WORD, "").strip()
                        if remainder:
                            self._process_input(remainder)
                        continue
                    if any(g in text.lower() for g in ["hello", "hi ", "hey "]):
                        self.state_machine.wake_up()
                        self._process_input(text)
                        continue

                elif self.state_machine.current_state == self.state_machine.listening:
                    text = self.speech_recognizer.get_result(timeout=10.0)
                    if text is None:
                        self.tts.speak(
                            "I didn't hear anything. Going back to standby."
                        )
                        self.state_machine.timeout()
                        continue
                    self._process_input(text)

            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                self.eye_display.expression = Expression.ERROR
                self.tts.speak("Sorry, I encountered an error. Please try again.")
                try:
                    self.state_machine.error()
                except Exception:
                    pass
                time.sleep(1.0)

    def _process_input(self, text: str):
        """Parse intent and generate response."""
        self.state_machine.hear_input()

        intent = self.intent_parser.parse(text)
        logger.info(f"Parsed intent: {intent}")

        response = self._generate_response(intent)
        self.state_machine.generate_response()

        self.tts.speak(response)
        self.state_machine.finish_response()

    def _generate_response(self, intent: ParsedIntent) -> str:
        """Generate a verbal response based on the parsed intent."""

        if intent.intent == "greeting":
            return (
                "Hello! Welcome to our campus. I can help you with "
                "directions, finding faculty, looking up students, "
                "or department information. Just ask me anything!"
            )

        elif intent.intent == "farewell":
            return "Goodbye! Have a great day. Feel free to ask me anytime."

        elif intent.intent == "help":
            return (
                "I can help you with several things. "
                "Ask me for directions to any building or department. "
                "Ask me about a professor or faculty member. "
                "Ask me to look up a student by name or roll number. "
                "Or ask me about department information. What would you like?"
            )

        elif intent.intent == "navigation":
            return self._handle_navigation(intent)

        elif intent.intent == "faculty_info":
            return self._handle_faculty_info(intent)

        elif intent.intent == "student_lookup":
            return self._handle_student_lookup(intent)

        elif intent.intent == "department_info":
            return self._handle_department_info(intent)

        else:
            return (
                "I'm sorry, I didn't understand that. "
                "You can ask me for directions, about faculty, "
                "students, or departments. Could you try rephrasing?"
            )

    def _handle_navigation(self, intent: ParsedIntent) -> str:
        """Handle navigation requests."""
        location_name = intent.entities.get("location")
        if not location_name:
            return "Where would you like to go? Please mention a specific location."

        location = self.database.search_location(location_name)
        if not location:
            return f"I couldn't find a location matching '{location_name}'. Could you try again?"

        dest_node = location["node_id"]
        source_node = "main_gate"

        route = self.database.get_route(source_node, dest_node)
        if route and route.get("video_path"):
            self.video_player.play(route["video_path"])

        directions = self.navigator.get_directions_text(source_node, dest_node)
        if directions:
            return directions

        return f"I know where {location['name']} is, but I couldn't calculate a route right now."

    def _handle_faculty_info(self, intent: ParsedIntent) -> str:
        """Handle faculty information requests."""
        faculty_name = intent.entities.get("faculty_name")
        if not faculty_name:
            return "Which faculty member would you like to know about?"

        results = self.database.search_faculty(faculty_name)
        if not results:
            return f"I couldn't find any faculty matching '{faculty_name}'."

        f = results[0]
        dept_cursor = self.database.conn.execute(
            "SELECT name FROM departments WHERE id = ?", (f["department_id"],)
        )
        dept_row = dept_cursor.fetchone()
        dept_name = dept_row["name"] if dept_row else "unknown department"

        return (
            f"{f['name']} is a {f['designation']} in the {dept_name}. "
            f"Their office is at {f['office_location']}. "
            f"You can reach them at {f['email']}."
        )

    def _handle_student_lookup(self, intent: ParsedIntent) -> str:
        """Handle student lookup requests."""
        query = intent.raw_text
        results = self.database.search_student(query)
        if not results:
            return "I couldn't find any student matching your query."

        s = results[0]
        dept_cursor = self.database.conn.execute(
            "SELECT name FROM departments WHERE id = ?", (s["department_id"],)
        )
        dept_row = dept_cursor.fetchone()
        dept_name = dept_row["name"] if dept_row else "unknown department"

        return (
            f"{s['name']}, roll number {s['roll_number']}, "
            f"is a year {s['year']} student in {dept_name}, "
            f"section {s['section']}."
        )

    def _handle_department_info(self, intent: ParsedIntent) -> str:
        """Handle department information requests."""
        dept_name = intent.entities.get("department_name")
        if not dept_name:
            depts = self.database.get_all_departments()
            names = [d["name"] for d in depts]
            return "We have the following departments: " + ", ".join(names) + "."

        dept = self.database.get_department_by_name(dept_name)
        if not dept:
            return f"I couldn't find a department matching '{dept_name}'."

        hod_name = "not assigned"
        if dept["head_faculty_id"]:
            hod_cursor = self.database.conn.execute(
                "SELECT name FROM faculty WHERE id = ?", (dept["head_faculty_id"],)
            )
            hod_row = hod_cursor.fetchone()
            if hod_row:
                hod_name = hod_row["name"]

        return (
            f"The {dept['name']} is located in {dept['building']}, "
            f"floor {dept['floor']}. The head of department is {hod_name}. "
            f"You can contact them at {dept['phone']}."
        )

    # ── Battery callbacks ─────────────────────────────────────

    def _on_low_battery(self, percent: float):
        logger.warning(f"Low battery: {percent:.1f}%")
        self.tts.speak(
            f"Warning: my battery is at {int(percent)} percent. "
            "Please consider charging me soon."
        )

    def _on_critical_battery(self, percent: float):
        logger.critical(f"Critical battery: {percent:.1f}%")
        self.tts.speak(
            "My battery is critically low. I need to shut down soon. "
            "Please plug me in."
        )

    # ── Shutdown ──────────────────────────────────────────────

    def shutdown(self):
        """Gracefully shut down all subsystems."""
        logger.info("Shutting down...")
        self._shutdown_event.set()
        self.tts.speak("Shutting down. Goodbye!")
        time.sleep(1.0)

        self.speech_recognizer.stop()
        self.eye_display.stop()
        self.power_monitor.stop()
        self.video_player.close()
        self.tts.close()
        self.database.close()
        logger.info("Shutdown complete.")


# ══════════════════════════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════════════════════════

def main():
    robot = CampusRobot()

    def signal_handler(sig, frame):
        robot.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        robot.start()
    except KeyboardInterrupt:
        robot.shutdown()


if __name__ == "__main__":
    main()
