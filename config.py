"""
Campus Robot Configuration
All constants, file paths, thresholds, and hardware pin assignments.
Environment variables override defaults where noted.
"""
import os
import platform
from pathlib import Path

# ── Base Paths ────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
VIDEOS_DIR = BASE_DIR / "videos"


# ── Platform Detection ────────────────────────────────────────
def is_raspberry_pi() -> bool:
    """Detect if running on Raspberry Pi hardware."""
    if platform.machine() not in ("aarch64", "armv7l"):
        return False
    try:
        with open("/proc/device-tree/model", "r") as f:
            return "raspberry pi" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


IS_PI = is_raspberry_pi()

# ── Speech Recognition (Vosk) ────────────────────────────────
VOSK_MODEL_PATH = str(DATA_DIR / "vosk-model-en-in-0.5")
SAMPLE_RATE = int(os.environ.get("ROBOT_SAMPLE_RATE", 16000))
AUDIO_CHANNELS = 1
AUDIO_CHUNK_SIZE = 4000  # ~250ms at 16kHz

# STT tuning
STT_PAUSE_THRESHOLD = 1.0         # seconds of silence before processing (was 2.0)
STT_PHRASE_TIME_LIMIT = 8         # max seconds per phrase (was 15)
STT_LISTEN_TIMEOUT = 3            # seconds to wait for speech start (was 5)
STT_DEVICE_RETRY_INTERVAL = 3     # seconds between mic reconnect attempts
STT_DEVICE_MAX_RETRIES = 5        # max reconnects before console fallback
POST_TTS_DRAIN_MS = 300           # ms to drain mic buffer after TTS ends

# ── Audio Preprocessing ──────────────────────────────────────
AUDIO_VAD_ENABLED = True
AUDIO_VAD_AGGRESSIVENESS = 2               # 0-3 (3 = most aggressive)
AUDIO_NOISE_REDUCE_ENABLED = True
AUDIO_NOISE_REDUCE_STATIONARY = True       # stationary noise only (fast on Pi)
AUDIO_AGC_ENABLED = True
AUDIO_AGC_TARGET_RMS = 3000.0              # target RMS level for int16 audio
AUDIO_AGC_MAX_GAIN = 4.0
AUDIO_AGC_MIN_GAIN = 0.5
AUDIO_NOISE_PROFILE_DURATION = 1.0         # seconds of ambient noise to capture
AUDIO_VAD_SPEECH_FRAME_RATIO = 0.3         # min fraction of speech frames to accept

# Vosk confidence scoring
VOSK_CONFIDENCE_ACCEPT = 0.70     # above this = accept as-is
VOSK_CONFIDENCE_LOW = 0.45        # below this = log for tuning
VOSK_LOG_LOW_CONFIDENCE = True

# ── Text-to-Speech (Piper) ───────────────────────────────────
PIPER_MODEL_PATH = str(MODELS_DIR / "en_US-amy-medium.onnx")
PIPER_CONFIG_PATH = str(MODELS_DIR / "en_US-amy-medium.onnx.json")
TTS_SAMPLE_RATE = 22050  # Piper default output rate
TTS_OUTPUT_DEVICE_INDEX = (
    int(os.environ["ROBOT_TTS_DEVICE"])
    if "ROBOT_TTS_DEVICE" in os.environ else None
)
MACOS_TTS_VOICE = "Samantha"  # macOS fallback voice

# ── Database ──────────────────────────────────────────────────
DB_PATH = str(DATA_DIR / "campus.db")

# ── Crawled Data Files ────────────────────────────────────────
FACULTY_DATA_PATH = str(DATA_DIR / "faculty_summary.json")
CRAWLED_DATA_PATH = str(DATA_DIR / "lourdes_matha_all_data.json")

# ── Campus Navigation Map ────────────────────────────────────
CAMPUS_MAP_PATH = str(DATA_DIR / "campus_map.json")

# ── Wake Word & Intent Recognition ───────────────────────────
WAKE_WORD = "hey robot"
ALWAYS_LISTEN = False  # True = no wake word needed, False = wake word mode
FUZZY_THRESHOLD = 70   # Minimum fuzzywuzzy score to consider a match
WAKE_WORD_THRESHOLD = 85         # fuzzy score for wake word (was 75)
MIN_INPUT_WORDS = 2              # min words to consider valid input (was 3)
MIN_INTENT_CONFIDENCE = 0.4      # below this, ask user to rephrase

# Wake word grammar mode (Indian accent variants)
WAKE_WORD_VARIANTS = [
    "hey robot", "hey robat", "hay robot", "hay robat",
    "he robot", "he robat", "hei robot", "hey robo",
    "a robot", "hey robert", "hey roba", "hey robort",
    "hey roboat", "hai robot", "hai robat",
]
WAKE_WORD_GRAMMAR_THRESHOLD = 0.60

# Grammar re-recognition for entity extraction (two-pass)
GRAMMAR_RERECOGNITION_ENABLED = True
GRAMMAR_MIN_CONFIDENCE = 0.50
ENTITY_STRONG_MATCH_THRESHOLD = 80   # fuzzy score above which no re-recognition needed

# ── Display (Pygame Eye Animation) ───────────────────────────
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
DISPLAY_FPS = 30
EYE_BG_COLOR = (0, 0, 0)          # Black background
SCLERA_COLOR = (255, 255, 255)     # White sclera
IRIS_COLOR = (50, 50, 50)          # Dark iris
PUPIL_COLOR = (0, 0, 0)           # Black pupil
ERROR_IRIS_COLOR = (180, 0, 0)    # Red iris for error state
IRIS_MARGIN = 4                    # pixels between iris edge and sclera

# Eye geometry (for 320x240 display)
LEFT_EYE_CENTER = (100, 120)
RIGHT_EYE_CENTER = (220, 120)
SCLERA_WIDTH = 60
SCLERA_HEIGHT = 40
IRIS_RADIUS = 14
PUPIL_RADIUS = 7

# ── Video Player ─────────────────────────────────────────────
VIDEO_DIR = str(VIDEOS_DIR)
MAX_VIDEO_FILE_SIZE_MB = 500       # reject videos larger than this

# ── Power Monitor (Waveshare UPS HAT) ────────────────────────
UPS_I2C_ADDRESS = 0x42           # INA219 I2C address
BATTERY_CHECK_INTERVAL = 30      # seconds
BATTERY_LOW_THRESHOLD = 20       # percent -- warn user
BATTERY_CRITICAL_THRESHOLD = 10  # percent -- initiate shutdown
BATTERY_STALE_THRESHOLD = 180    # seconds before readings are considered stale
BATTERY_MAX_READ_FAILURES = 3    # consecutive I2C failures before reporting -1
BATTERY_ALERT_COOLDOWN = 300     # seconds between repeated alerts at same level

# ── GPIO / Hardware (ReSpeaker 2-Mic HAT) ────────────────────
RESPEAKER_DEVICE_INDEX = int(os.environ.get("ROBOT_MIC_DEVICE", 2))
BUTTON_GPIO_PIN = 17             # Physical button for interaction

# ── LED Status Colors (RGB tuples) ───────────────────────────
LED_IDLE = (0, 0, 50)            # Dim blue
LED_LISTENING = (0, 255, 0)      # Green
LED_PROCESSING = (255, 165, 0)   # Orange
LED_SPEAKING = (0, 0, 255)       # Blue
LED_ERROR = (255, 0, 0)          # Red

# ── Thread Communication ─────────────────────────────────────
AUDIO_QUEUE_MAXSIZE = 10
STATE_UPDATE_INTERVAL = 0.05     # seconds

# ── Error Recovery ───────────────────────────────────────────
SHUTDOWN_TIMEOUT = 10.0
MAX_ERROR_RETRIES = 5            # consecutive errors before sleep mode
ERROR_COOLDOWN = 2.0             # seconds between error retries

# ── Logging ──────────────────────────────────────────────────
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "robot.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per log file
LOG_BACKUP_COUNT = 3
LOG_LEVEL = os.environ.get("ROBOT_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s [%(session_id)s]: %(message)s"
LOW_CONFIDENCE_LOG_FILE = str(LOG_DIR / "low_confidence.jsonl")
