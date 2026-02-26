"""
Campus Guide Robot - Main Entry Point
State machine controller coordinating all subsystems.
"""
import logging
import logging.handlers
import signal
import sys
import threading
import time
import uuid

from statemachine import StateMachine, State

from fuzzywuzzy import fuzz

from config import (
    DB_PATH, CAMPUS_MAP_PATH, WAKE_WORD, FUZZY_THRESHOLD,
    ALWAYS_LISTEN, WAKE_WORD_THRESHOLD, MIN_INPUT_WORDS,
    MIN_INTENT_CONFIDENCE, MAX_ERROR_RETRIES, ERROR_COOLDOWN,
    SHUTDOWN_TIMEOUT, LOG_DIR, LOG_FILE, LOG_MAX_BYTES,
    LOG_BACKUP_COUNT, LOG_LEVEL, LOG_FORMAT,
    VOSK_CONFIDENCE_LOW, VOSK_LOG_LOW_CONFIDENCE,
    LOW_CONFIDENCE_LOG_FILE,
    WAKE_WORD_VARIANTS,
    GRAMMAR_RERECOGNITION_ENABLED, ENTITY_STRONG_MATCH_THRESHOLD,
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
SESSION_ID = uuid.uuid4().hex[:8]


class _SessionFilter(logging.Filter):
    """Inject session_id into every log record."""
    def filter(self, record):
        record.session_id = SESSION_ID
        return True


def _setup_logging():
    """Configure rotating file + console logging with session ID."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    session_filter = _SessionFilter()

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # Console handler — filter on the handler so propagated records get session_id
    console = logging.StreamHandler()
    console.addFilter(session_filter)
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        str(LOG_FILE), maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
    )
    file_handler.addFilter(session_filter)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_handler)


_setup_logging()
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
        self._state_lock = threading.RLock()
        self._is_awake_lock = threading.Lock()
        self._is_awake = False
        self._consecutive_errors = 0

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

    # ── Thread-safe is_awake access ────────────────────────────

    @property
    def is_awake(self) -> bool:
        with self._is_awake_lock:
            return self._is_awake

    @is_awake.setter
    def is_awake(self, value: bool):
        with self._is_awake_lock:
            self._is_awake = value

    # ── Thread-safe state transitions ──────────────────────────

    def _safe_transition(self, transition_name: str) -> bool:
        """Execute a state machine transition under lock. Returns True on success."""
        with self._state_lock:
            try:
                getattr(self.state_machine, transition_name)()
                return True
            except Exception as e:
                logger.warning(f"State transition '{transition_name}' failed: {e}")
                return False

    def _force_idle(self):
        """Force the state machine back to idle, even if normal transitions fail."""
        with self._state_lock:
            try:
                self.state_machine.error()
            except Exception:
                # Direct state reset as last resort
                try:
                    self.state_machine._current_state = self.state_machine.idle
                    logger.warning("Forced state machine to idle via direct reset")
                except Exception as e:
                    logger.error(f"Cannot reset state machine: {e}")

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self):
        """Start all subsystem threads and enter the main loop."""
        logger.info("Starting subsystems...")
        self.eye_display.start()
        self.speech_recognizer.start()
        self.power_monitor.start()

        self.tts.speak(
            "Hello! I am your campus guide robot. "
            "Say 'hey robot' to wake me up.",
            blocking=True,
        )

        self._main_loop()

    def _main_loop(self):
        """Main event loop. Reads from speech recognizer and drives state machine."""
        logger.info("Entering main loop...")

        while not self._shutdown_event.is_set():
            try:
                with self._state_lock:
                    current = self.state_machine.current_state

                if current == self.state_machine.idle:
                    result = self.speech_recognizer.get_result(timeout=0.1)
                    if result is None:
                        continue

                    # Extract text and confidence from RecognitionResult
                    text = str(result)
                    confidence = getattr(result, "confidence", 1.0)

                    # Log low-confidence results for tuning
                    if VOSK_LOG_LOW_CONFIDENCE and confidence < VOSK_CONFIDENCE_LOW:
                        self._log_low_confidence(result)

                    # ── Sleeping: wait for wake word ──
                    if not self.is_awake:
                        if self._matches_wake_word(text):
                            self.is_awake = True
                            self.speech_recognizer.set_recognition_mode("open")
                            logger.info("Robot AWAKE — listening for questions")
                            self.tts.speak("I'm awake! Ask me anything.")
                        continue

                    # ── Awake: process everything ──
                    words = text.strip().split()
                    if len(words) < MIN_INPUT_WORDS:
                        logger.debug(f"Ignoring short input: '{text}'")
                        continue

                    if self._safe_transition("wake_up"):
                        self._process_input(text)

                    # Reset error counter on successful iteration
                    self._consecutive_errors = 0

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"Error in main loop ({self._consecutive_errors}/{MAX_ERROR_RETRIES}): {e}", exc_info=True)
                self.eye_display.expression = Expression.ERROR

                if self._consecutive_errors >= MAX_ERROR_RETRIES:
                    logger.critical("Max consecutive errors reached — entering sleep mode")
                    self.eye_display.expression = Expression.SLEEPING
                    self.is_awake = False
                    self.speech_recognizer.set_recognition_mode("wake")
                    self._consecutive_errors = 0
                    self._force_idle()
                    self.tts.speak("I'm having trouble. Going to sleep. Say 'hey robot' to try again.")
                else:
                    # Avoid TTS during error recovery if TTS itself might be broken
                    try:
                        self.tts.speak("Sorry, I encountered an error. Please try again.")
                    except Exception:
                        logger.error("TTS also failed during error recovery")
                    self._force_idle()

                time.sleep(ERROR_COOLDOWN)

    # ── Low-confidence logging ────────────────────────────────

    def _log_low_confidence(self, result):
        """Append low-confidence recognition results to JSONL file for tuning."""
        import json as _json
        import datetime
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "text": str(result),
                "confidence": getattr(result, "confidence", 0.0),
                "word_confidences": getattr(result, "word_confidences", []),
                "source": getattr(result, "source", "unknown"),
                "session": SESSION_ID,
            }
            with open(LOW_CONFIDENCE_LOG_FILE, "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug(f"Failed to log low-confidence result: {e}")

    # ── Wake word matching ─────────────────────────────────────

    def _matches_wake_word(self, text: str) -> bool:
        """Multi-layer wake word validation with Indian accent variant support.

        Checks in order:
        1. Exact match against canonical wake word
        2. Exact match against any known variant (grammar mode outputs these)
        3. Fuzzy matching with token-level validation
        """
        text_lower = text.lower().strip()
        wake_words = WAKE_WORD.lower().split()

        # Guard: input must have at least as many words as wake phrase
        text_words = text_lower.split()
        if len(text_words) < len(wake_words):
            return False

        # Fast path: exact substring for canonical wake word
        if WAKE_WORD in text_lower:
            return True

        # Check against all known variants (grammar mode will output these)
        for variant in WAKE_WORD_VARIANTS:
            if variant.lower() in text_lower:
                logger.info(f"Wake word variant match: '{text}' → '{variant}'")
                return True

        # Fuzzy partial_ratio with configurable threshold
        score = fuzz.partial_ratio(WAKE_WORD, text_lower)
        if score < WAKE_WORD_THRESHOLD:
            return False

        # Token-level validation: each wake word must have a close match
        for wake_token in wake_words:
            best_token_score = max(
                fuzz.ratio(wake_token, word) for word in text_words
            )
            if best_token_score < 60:
                return False

        logger.info(f"Wake word fuzzy match: '{text}' (score={score})")
        return True

    # ── Input processing ───────────────────────────────────────

    def _process_input(self, text: str):
        """Parse intent and generate response.

        Two-pass recognition: if the entity match is weak, re-recognize
        the audio buffer using a grammar-constrained recognizer for better
        entity accuracy.
        """
        self._safe_transition("hear_input")

        intent = self.intent_parser.parse(text)
        logger.info(f"Parsed intent: {intent}")

        # Confidence gate
        if intent.confidence < MIN_INTENT_CONFIDENCE and intent.intent == "unknown":
            self._safe_transition("generate_response")
            self.tts.speak(
                "I'm not sure I understood that. Could you try rephrasing?",
                on_complete=self._on_speech_complete,
            )
            return

        # Two-pass: grammar re-recognition for weak entity matches
        intent = self._try_grammar_rerecognition(intent)

        response = self._generate_response(intent)
        self._safe_transition("generate_response")

        # Async TTS — state transitions back to idle via callback
        self.tts.speak(response, on_complete=self._on_speech_complete)

        # Go back to sleep on farewell
        if intent.intent == "farewell":
            self.is_awake = False
            self.speech_recognizer.set_recognition_mode("wake")
            logger.info("Robot SLEEPING — waiting for wake word")

    def _try_grammar_rerecognition(self, intent: ParsedIntent) -> ParsedIntent:
        """If entity match is weak, re-recognize audio with grammar constraints.

        Returns the original or improved ParsedIntent.
        """
        if not GRAMMAR_RERECOGNITION_ENABLED:
            return intent
        if intent.intent in ("greeting", "farewell", "help", "unknown"):
            return intent

        # Check if any entity score is below the strong-match threshold
        entity_scores = [
            intent.entities.get("location_score", 100),
            intent.entities.get("faculty_score", 100),
            intent.entities.get("department_score", 100),
        ]
        if all(s >= ENTITY_STRONG_MATCH_THRESHOLD for s in entity_scores):
            return intent  # All entities matched strongly, no need to re-recognize

        # Get grammar for this intent type
        grammar = self.intent_parser.get_entity_grammar(intent.intent)
        if not grammar:
            return intent

        # Try grammar-constrained re-recognition
        grammar_result = self.speech_recognizer.recognize_with_grammar(grammar)
        if grammar_result is None:
            return intent

        # Re-parse with the grammar-enhanced text
        grammar_text = str(grammar_result)
        if grammar_text:
            enhanced_intent = self.intent_parser.parse(grammar_text)
            # Only use the enhanced result if it improved entity matching
            enhanced_scores = [
                enhanced_intent.entities.get("location_score", 0),
                enhanced_intent.entities.get("faculty_score", 0),
                enhanced_intent.entities.get("department_score", 0),
            ]
            if max(enhanced_scores) > max(s for s in entity_scores if s < 100):
                logger.info(
                    f"Grammar re-recognition improved entity: "
                    f"'{intent.raw_text}' → '{grammar_text}'"
                )
                # Keep the original intent type but use enhanced entities
                return ParsedIntent(
                    intent=intent.intent,
                    confidence=intent.confidence,
                    entities=enhanced_intent.entities,
                    raw_text=intent.raw_text,
                )

        return intent

    def _on_speech_complete(self, completed: bool):
        """Callback from TTS thread when speech finishes."""
        if completed:
            logger.debug("Speech completed naturally")
        else:
            logger.debug("Speech was interrupted")
        self._safe_transition("finish_response")

    def _generate_response(self, intent: ParsedIntent) -> str:
        """Generate a verbal response based on the parsed intent."""

        if intent.intent == "greeting":
            return (
                "Hello! Welcome to our campus. I can help you with "
                "directions, finding faculty, looking up students, "
                "department information, or general campus queries "
                "like hostel, library, admissions, and more. Just ask me anything!"
            )

        elif intent.intent == "farewell":
            return "Goodbye! Have a great day. Feel free to ask me anytime."

        elif intent.intent == "help":
            return (
                "I can help you with several things. "
                "Ask me for directions to any building or department. "
                "Ask me about a professor or faculty member. "
                "Ask me to look up a student by name or roll number. "
                "Ask about department information. "
                "Or ask me about campus facilities like the hostel, "
                "library, admissions, courses, and more. What would you like?"
            )

        elif intent.intent == "navigation":
            return self._handle_navigation(intent)

        elif intent.intent == "faculty_info":
            return self._handle_faculty_info(intent)

        elif intent.intent == "student_lookup":
            return self._handle_student_lookup(intent)

        elif intent.intent == "department_info":
            return self._handle_department_info(intent)

        elif intent.intent == "campus_info":
            return self._handle_campus_info(intent)

        else:
            # Try knowledge base before giving up
            kb_response = self._handle_campus_info(intent)
            if kb_response:
                return kb_response
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
            self.video_player.wait_for_completion(timeout=300)

        directions = self.navigator.get_directions_text(source_node, dest_node)
        if directions:
            return directions

        return f"I know where {location['name']} is, but I couldn't calculate a route right now."

    # Role keywords that trigger designation-based search
    _ROLE_KEYWORDS = [
        "principal", "vice principal", "dean", "chairman",
        "director", "hod", "head of department", "coordinator",
    ]

    # College name shortcuts
    _COLLEGE_ALIASES = {
        "lmcst": "LMCST", "lmims": "LMIMS", "lmihmct": "LMIHMCT",
        "lmcas": "LMCAS", "lourdes matha": "Lourdes Matha",
    }

    def _handle_faculty_info(self, intent: ParsedIntent) -> str:
        """Handle faculty information requests (by name or by role)."""
        text_lower = intent.raw_text.lower()
        faculty_name = intent.entities.get("faculty_name")

        # Check if this is a role-based query (principal, HOD, dean, etc.)
        role_match = None
        for role in self._ROLE_KEYWORDS:
            if role in text_lower:
                role_match = role
                break

        if role_match:
            # Extract college name from query if mentioned
            college_filter = None
            for alias, name in self._COLLEGE_ALIASES.items():
                if alias in text_lower:
                    college_filter = alias
                    break

            results = self.database.search_faculty_by_role(role_match, college_filter)
            if results:
                f = results[0]
                college = f.get("college_short_name") or f.get("college_name") or ""
                response = f"The {f['designation']} is {f['name']}"
                if college:
                    response += f" at {college}"
                response += "."
                if f.get("qualification"):
                    response += f" Qualification: {f['qualification']}."
                if f.get("email"):
                    response += f" Email: {f['email']}."
                return response
            return f"I couldn't find a {role_match} in our records."

        # Name-based search
        if faculty_name:
            results = self.database.search_faculty(faculty_name)
            if results:
                return self._format_faculty_result(results[0])
            return f"I couldn't find any faculty matching '{faculty_name}'."

        # Try searching the raw text against faculty names as last resort
        results = self.database.search_faculty(intent.raw_text)
        if results:
            return self._format_faculty_result(results[0])

        return "Which faculty member would you like to know about?"

    def _format_faculty_result(self, f: dict) -> str:
        """Format a faculty record into a spoken response."""
        dept_name = f.get("department_name") or "unknown department"
        college_name = f.get("college_short_name") or f.get("college_name") or ""

        parts = [f"{f['name']} is a {f['designation']} in {dept_name}"]
        if college_name:
            parts[0] += f" at {college_name}"
        parts[0] += "."

        if f.get("qualification"):
            parts.append(f"Qualification: {f['qualification']}.")
        if f.get("office_location"):
            parts.append(f"Their office is at {f['office_location']}.")
        if f.get("email"):
            parts.append(f"Email: {f['email']}.")

        return " ".join(parts)

    def _handle_student_lookup(self, intent: ParsedIntent) -> str:
        """Handle student lookup requests using JOIN query."""
        query = intent.raw_text
        results = self.database.search_student_with_department(query)
        if not results:
            return "I couldn't find any student matching your query."

        s = results[0]
        dept_name = s.get("department_name") or "unknown department"

        return (
            f"{s['name']}, roll number {s['roll_number']}, "
            f"is a year {s['year']} student in {dept_name}, "
            f"section {s['section']}."
        )

    _STOP_WORDS = {"can", "you", "tell", "me", "about", "the", "a", "an",
                    "is", "are", "what", "where", "how", "do", "have", "i",
                    "to", "of", "in", "at", "for", "and", "or", "this",
                    "that", "it", "be", "was", "there", "any", "some"}

    def _handle_campus_info(self, intent: ParsedIntent) -> str:
        """Handle general campus information queries using the knowledge base."""
        query = intent.raw_text

        # Extract meaningful words for better search
        meaningful_words = [w for w in query.split()
                           if w.lower() not in self._STOP_WORDS]
        if len(meaningful_words) < 1:
            return ""

        # Search with meaningful words for better relevance
        clean_query = " ".join(meaningful_words)
        results = self.database.search_knowledge_base(clean_query)
        if not results:
            return ""

        # Use the top matching paragraph, keep it short for speech
        top = results[0]
        content = top["content"]

        # Cut at the first sentence boundary around 200 chars for natural speech
        if len(content) > 200:
            cut = content[:200].rfind(".")
            if cut > 50:
                content = content[:cut + 1]
            else:
                content = content[:200] + "..."

        return content

    def _handle_department_info(self, intent: ParsedIntent) -> str:
        """Handle department information requests."""
        dept_name = intent.entities.get("department_name")
        if not dept_name:
            depts = self.database.get_all_departments()
            names = [d["name"] for d in depts]
            return "We have the following departments: " + ", ".join(names) + "."

        # Try the new JOIN-based lookup first for HOD info
        dept_with_head = self.database.get_department_with_head(dept_name)
        if dept_with_head:
            dept = dept_with_head
        else:
            dept = self.database.get_department_by_name(dept_name)

        if not dept:
            return f"I couldn't find a department matching '{dept_name}'."

        college_name = dept.get("college_short_name") or dept.get("college_name") or ""
        parts = [f"The {dept['name']}"]
        if college_name:
            parts[0] += f" is part of {college_name}"
        parts[0] += "."

        if dept.get("building"):
            parts.append(f"It is located in {dept['building']}, floor {dept.get('floor', 0)}.")

        # Use HOD name from JOIN if available
        head_name = dept.get("head_name")
        if head_name:
            parts.append(f"The head of department is {head_name}.")
        elif dept.get("head_faculty_id"):
            # Fallback to separate query via thread-safe helper
            hod = self.database._fetchone(
                "SELECT name FROM faculty WHERE id = ?", (dept["head_faculty_id"],)
            )
            if hod:
                parts.append(f"The head of department is {hod['name']}.")

        faculty_count = len(self.database.get_faculty_by_department(dept["id"]))
        if faculty_count:
            parts.append(f"It has {faculty_count} faculty members.")

        if dept.get("phone"):
            parts.append(f"You can contact them at {dept['phone']}.")

        return " ".join(parts)

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
        if self._shutdown_event.is_set():
            return  # Already shutting down
        logger.info("Shutting down...")
        self._shutdown_event.set()

        try:
            self.tts.speak("Shutting down. Goodbye!", blocking=True)
        except Exception:
            pass

        # Shut down each subsystem individually — never let one crash stop the rest
        for name, subsystem, method in [
            ("speech_recognizer", self.speech_recognizer, "stop"),
            ("eye_display", self.eye_display, "stop"),
            ("power_monitor", self.power_monitor, "stop"),
            ("video_player", self.video_player, "close"),
            ("tts", self.tts, "close"),
            ("database", self.database, "close"),
        ]:
            try:
                getattr(subsystem, method)()
            except Exception as e:
                logger.error(f"Error shutting down {name}: {e}")

        logger.info("Shutdown complete.")


# ══════════════════════════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════════════════════════

def main():
    robot = CampusRobot()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        robot.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Ignore broken pipe (prevents crash when piping output)
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    except AttributeError:
        pass  # SIGPIPE not available on Windows

    try:
        robot.start()
    except KeyboardInterrupt:
        robot.shutdown()


if __name__ == "__main__":
    main()
