"""
Piper TTS wrapper for offline text-to-speech synthesis.
Falls back to print-only mode when Piper or audio output is unavailable.
"""
import io
import logging
import threading
import wave
from typing import Optional

from config import PIPER_MODEL_PATH, PIPER_CONFIG_PATH

logger = logging.getLogger(__name__)

try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logger.warning("Piper TTS not available. Using print fallback.")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


class TextToSpeech:
    """
    Synthesize speech from text using Piper TTS.
    Sets a shared is_speaking flag for echo prevention.
    """

    def __init__(self, is_speaking_event: threading.Event):
        self.is_mock = not PIPER_AVAILABLE
        self._is_speaking = is_speaking_event
        self._voice: Optional[PiperVoice] = None
        self._audio = None
        self._lock = threading.Lock()

        if not self.is_mock:
            try:
                logger.info(f"Loading Piper model: {PIPER_MODEL_PATH}")
                self._voice = PiperVoice.load(
                    PIPER_MODEL_PATH,
                    config_path=PIPER_CONFIG_PATH,
                )
                logger.info("Piper TTS model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load Piper model: {e}")
                self.is_mock = True

        if PYAUDIO_AVAILABLE and not self.is_mock:
            self._audio = pyaudio.PyAudio()

    def speak(self, text: str):
        """Synthesize and play the given text. Thread-safe."""
        with self._lock:
            if self.is_mock:
                self._mock_speak(text)
                return
            self._piper_speak(text)

    def _piper_speak(self, text: str):
        """Synthesize with Piper and play via PyAudio."""
        self._is_speaking.set()
        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file)

            wav_buffer.seek(0)
            with wave.open(wav_buffer, "rb") as wav_file:
                stream = self._audio.open(
                    format=self._audio.get_format_from_width(wav_file.getsampwidth()),
                    channels=wav_file.getnchannels(),
                    rate=wav_file.getframerate(),
                    output=True,
                )
                chunk_size = 1024
                data = wav_file.readframes(chunk_size)
                while data:
                    stream.write(data)
                    data = wav_file.readframes(chunk_size)
                stream.stop_stream()
                stream.close()
        except Exception as e:
            logger.error(f"TTS playback error: {e}")
        finally:
            self._is_speaking.clear()

    def _mock_speak(self, text: str):
        """Print text to console as a fallback."""
        self._is_speaking.set()
        print(f"[ROBOT SAYS]: {text}")
        self._is_speaking.clear()

    def close(self):
        """Clean up audio resources."""
        if self._audio:
            self._audio.terminate()
