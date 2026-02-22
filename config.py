"""
Campus Robot Configuration
All constants, file paths, thresholds, and hardware pin assignments.
"""
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
VOSK_MODEL_PATH = str(DATA_DIR / "vosk-model-small-en-us-0.15")
SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_CHUNK_SIZE = 4000  # ~250ms at 16kHz

# ── Text-to-Speech (Piper) ───────────────────────────────────
PIPER_MODEL_PATH = str(MODELS_DIR / "en_US-amy-medium.onnx")
PIPER_CONFIG_PATH = str(MODELS_DIR / "en_US-amy-medium.onnx.json")
TTS_SAMPLE_RATE = 22050  # Piper default output rate

# ── Database ──────────────────────────────────────────────────
DB_PATH = str(DATA_DIR / "campus.db")

# ── Crawled Data Files ────────────────────────────────────────
FACULTY_DATA_PATH = str(DATA_DIR / "faculty_summary.json")
CRAWLED_DATA_PATH = str(DATA_DIR / "lourdes_matha_all_data.json")

# ── Campus Navigation Map ────────────────────────────────────
CAMPUS_MAP_PATH = str(DATA_DIR / "campus_map.json")

# ── Wake Word & Intent Recognition ───────────────────────────
WAKE_WORD = "hey robot"
FUZZY_THRESHOLD = 70  # Minimum fuzzywuzzy score to consider a match

# ── Display (Pygame Eye Animation) ───────────────────────────
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
DISPLAY_FPS = 30
EYE_BG_COLOR = (0, 0, 0)          # Black background
SCLERA_COLOR = (255, 255, 255)     # White sclera
IRIS_COLOR = (50, 50, 50)          # Dark iris
PUPIL_COLOR = (0, 0, 0)           # Black pupil

# Eye geometry (for 320x240 display)
LEFT_EYE_CENTER = (100, 120)
RIGHT_EYE_CENTER = (220, 120)
SCLERA_WIDTH = 60
SCLERA_HEIGHT = 40
IRIS_RADIUS = 14
PUPIL_RADIUS = 7

# ── Video Player ─────────────────────────────────────────────
VIDEO_DIR = str(VIDEOS_DIR)

# ── Power Monitor (Waveshare UPS HAT) ────────────────────────
UPS_I2C_ADDRESS = 0x42           # INA219 I2C address
BATTERY_CHECK_INTERVAL = 30      # seconds
BATTERY_LOW_THRESHOLD = 20       # percent -- warn user
BATTERY_CRITICAL_THRESHOLD = 10  # percent -- initiate shutdown

# ── GPIO / Hardware (ReSpeaker 2-Mic HAT) ────────────────────
RESPEAKER_DEVICE_INDEX = 2       # Default, may vary per system
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
