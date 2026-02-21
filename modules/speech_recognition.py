"""
Vosk-based offline speech recognition wrapper.
Falls back to console text input on non-Pi platforms or when
Vosk/PyAudio are not available.
"""
import json
import logging
import queue
import threading
from typing import Optional

from config import (
    VOSK_MODEL_PATH, SAMPLE_RATE, AUDIO_CHUNK_SIZE,
    AUDIO_CHANNELS, WAKE_WORD,
)

logger = logging.getLogger(__name__)

try:
    import vosk
    import pyaudio
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logger.warning("Vosk/PyAudio not available. Using console input fallback.")


class SpeechRecognizer:
    """
    Streaming speech recognizer using Vosk.

    On platforms without Vosk/PyAudio, falls back to blocking
    console input (useful for Windows development/testing).
    """

    def __init__(self):
        self.is_mock = not VOSK_AVAILABLE
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._result_queue: queue.Queue = queue.Queue()
        self._is_speaking = threading.Event()

        if not self.is_mock:
            try:
                vosk.SetLogLevel(-1)
                logger.info(f"Loading Vosk model from: {VOSK_MODEL_PATH}")
                self._model = vosk.Model(VOSK_MODEL_PATH)
                self._recognizer = vosk.KaldiRecognizer(self._model, SAMPLE_RATE)
                self._recognizer.SetWords(True)
                self._audio = pyaudio.PyAudio()
                self._stream = None
            except Exception as e:
                logger.error(f"Failed to initialize Vosk: {e}")
                self.is_mock = True

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking.is_set()

    @is_speaking.setter
    def is_speaking(self, value: bool):
        if value:
            self._is_speaking.set()
        else:
            self._is_speaking.clear()

    def start(self):
        """Start the recognition loop in a background thread."""
        self._running = True
        if self.is_mock:
            self._thread = threading.Thread(
                target=self._console_input_loop, daemon=True
            )
        else:
            self._thread = threading.Thread(
                target=self._vosk_recognition_loop, daemon=True
            )
        self._thread.start()
        logger.info("Speech recognizer started (mock=%s)", self.is_mock)

    def stop(self):
        """Stop the recognition loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if not self.is_mock:
            try:
                if self._stream:
                    self._stream.stop_stream()
                    self._stream.close()
                self._audio.terminate()
            except Exception:
                pass
        logger.info("Speech recognizer stopped.")

    def get_result(self, timeout: float = None) -> Optional[str]:
        """Get the next recognized text from the queue."""
        try:
            return self._result_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _vosk_recognition_loop(self):
        """Main Vosk streaming recognition loop (runs in audio thread)."""
        try:
            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=AUDIO_CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK_SIZE,
            )
            self._stream.start_stream()
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            self.is_mock = True
            self._console_input_loop()
            return

        logger.info("Vosk listening...")

        while self._running:
            try:
                data = self._stream.read(AUDIO_CHUNK_SIZE, exception_on_overflow=False)
            except Exception as e:
                logger.error(f"Audio read error: {e}")
                continue

            if self._is_speaking.is_set():
                continue

            if self._recognizer.AcceptWaveform(data):
                result_json = self._recognizer.Result()
                result = json.loads(result_json)
                text = result.get("text", "").strip()
                if text:
                    logger.info(f"Recognized: {text}")
                    self._result_queue.put(text)

    def _console_input_loop(self):
        """Fallback: read text from console (for development on Windows)."""
        print("\n[MOCK STT] Type your speech input (or 'quit' to exit):")
        while self._running:
            try:
                text = input("[You]: ").strip()
                if text.lower() == "quit":
                    self._running = False
                    break
                if text:
                    self._result_queue.put(text)
            except EOFError:
                break
