"""
Speech recognition module.
Uses SpeechRecognition library for proper silence detection + Vosk for
offline recognition. Falls back to console text input when unavailable.

Phase 3 hardening:
- Bounded result queue with oldest-discard policy
- Device selection (ReSpeaker on Pi, default elsewhere)
- Model path validation
- Tighter silence detection parameters
- Partial result streaming (raw_vosk)
- Device error recovery with automatic reconnect
- Efficient echo prevention (event-based, no busy loops)
- Clean shutdown for both backends

Phase 6 enhancements:
- RecognitionResult dataclass with confidence scoring
- Word-level confidence extraction from Vosk
"""
import json
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from config import (
    VOSK_MODEL_PATH,
    IS_PI,
    SAMPLE_RATE,
    AUDIO_QUEUE_MAXSIZE,
    RESPEAKER_DEVICE_INDEX,
    STT_PAUSE_THRESHOLD,
    STT_PHRASE_TIME_LIMIT,
    STT_LISTEN_TIMEOUT,
    STT_DEVICE_RETRY_INTERVAL,
    STT_DEVICE_MAX_RETRIES,
    POST_TTS_DRAIN_MS,
    AUDIO_NOISE_PROFILE_DURATION,
    WAKE_WORD_VARIANTS,
)

logger = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    """Result of speech recognition with confidence metadata.

    Provides backward compatibility via __str__ so existing code
    that treats results as plain strings continues to work.
    """
    text: str
    confidence: float = 1.0                   # 0.0–1.0, mean of word confidences
    word_confidences: list[dict] = field(default_factory=list)  # [{word, conf, start, end}]
    is_final: bool = True
    source: str = "vosk"                      # "vosk", "google", or "console"

    def __str__(self) -> str:
        return self.text

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return self.text == other
        if isinstance(other, RecognitionResult):
            return self.text == other.text
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.text)

    @staticmethod
    def from_vosk_result(result_dict: dict) -> "RecognitionResult":
        """Create a RecognitionResult from a parsed Vosk JSON result."""
        text = result_dict.get("text", "").strip()
        word_confidences = []
        total_conf = 0.0

        vosk_words = result_dict.get("result", [])
        for w in vosk_words:
            word_confidences.append({
                "word": w.get("word", ""),
                "conf": w.get("conf", 0.0),
                "start": w.get("start", 0.0),
                "end": w.get("end", 0.0),
            })
            total_conf += w.get("conf", 0.0)

        confidence = total_conf / len(vosk_words) if vosk_words else 0.0
        return RecognitionResult(
            text=text,
            confidence=confidence,
            word_confidences=word_confidences,
            source="vosk",
        )

# Try SpeechRecognition library (provides proper silence detection)
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

# Try raw Vosk (for Pi streaming mode)
try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False


class SpeechRecognizer:
    """
    Speech recognizer with proper silence detection.
    Uses SpeechRecognition library + Vosk backend for fully offline operation.

    Hardened with bounded queues, device recovery, partial-result streaming,
    and efficient echo prevention.
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._result_queue: queue.Queue = queue.Queue(maxsize=AUDIO_QUEUE_MAXSIZE)
        self._is_speaking = threading.Event()
        self._consecutive_errors = 0
        self._on_partial: Optional[Callable[[str], None]] = None

        if SR_AVAILABLE and VOSK_AVAILABLE:
            self._backend = "sr_vosk"
            self._init_sr_vosk()
        elif VOSK_AVAILABLE:
            self._backend = "raw_vosk"
            self._init_raw_vosk()
        else:
            self._backend = "console"

        logger.info(f"Speech recognition backend: {self._backend}")

    # ── Queue helper ──────────────────────────────────────────

    def _enqueue_result(self, result):
        """Put a RecognitionResult on the bounded queue; if full, discard oldest.

        Accepts either a RecognitionResult or a plain string (wrapped
        automatically for backward compatibility).
        """
        if isinstance(result, str):
            result = RecognitionResult(text=result, confidence=1.0, source=self._backend)
        if self._result_queue.full():
            try:
                discarded = self._result_queue.get_nowait()
                logger.warning(
                    f"Result queue full — discarded oldest item: {discarded!r}"
                )
            except queue.Empty:
                pass
        self._result_queue.put(result)

    # ── Partial result callback ───────────────────────────────

    @property
    def on_partial(self) -> Optional[Callable[[str], None]]:
        """Callback invoked with partial recognition text (raw_vosk only)."""
        return self._on_partial

    @on_partial.setter
    def on_partial(self, callback: Optional[Callable[[str], None]]):
        self._on_partial = callback

    # ── Initialization ────────────────────────────────────────

    def _validate_model_path(self):
        """Raise FileNotFoundError if the Vosk model directory is missing."""
        if not os.path.isdir(VOSK_MODEL_PATH):
            raise FileNotFoundError(
                f"Vosk model directory not found: {VOSK_MODEL_PATH}. "
                "Download the model and place it in the data/ folder."
            )

    def _init_sr_vosk(self):
        """Initialize SpeechRecognition (for silence detection) + Vosk (for recognition)."""
        self._validate_model_path()

        self._sr_recognizer = sr.Recognizer()
        self._sr_mic = sr.Microphone(
            device_index=RESPEAKER_DEVICE_INDEX if IS_PI else None,
            sample_rate=SAMPLE_RATE,
        )

        # Load our own Vosk model
        vosk.SetLogLevel(-1)
        logger.info(f"Loading Vosk model from: {VOSK_MODEL_PATH}")
        self._vosk_model = vosk.Model(VOSK_MODEL_PATH)

        # Calibrate for ambient noise
        logger.info("Calibrating microphone for ambient noise...")
        with self._sr_mic as source:
            self._sr_recognizer.adjust_for_ambient_noise(source, duration=1)

        # Tighter silence detection settings
        self._sr_recognizer.pause_threshold = STT_PAUSE_THRESHOLD
        self._sr_recognizer.phrase_threshold = 0.3
        self._sr_recognizer.non_speaking_duration = 0.5

    def _init_raw_vosk(self):
        """Initialize raw Vosk backend (for Pi)."""
        self._validate_model_path()

        import pyaudio
        from config import AUDIO_CHUNK_SIZE, AUDIO_CHANNELS

        vosk.SetLogLevel(-1)
        logger.info(f"Loading Vosk model from: {VOSK_MODEL_PATH}")
        self._model = vosk.Model(VOSK_MODEL_PATH)

        # Dual recognizer: open-vocabulary + grammar-constrained wake word
        self._open_recognizer = vosk.KaldiRecognizer(self._model, SAMPLE_RATE)
        self._open_recognizer.SetWords(True)

        # Grammar-constrained recognizer for wake word detection
        grammar = json.dumps(WAKE_WORD_VARIANTS + ["[unk]"])
        self._wake_recognizer = vosk.KaldiRecognizer(
            self._model, SAMPLE_RATE, grammar
        )
        self._wake_recognizer.SetWords(True)

        # Start in wake mode
        self._recognition_mode = "wake"
        self._recognizer = self._wake_recognizer

        self._audio = pyaudio.PyAudio()
        self._stream = None
        self._chunk_size = AUDIO_CHUNK_SIZE
        self._channels = AUDIO_CHANNELS
        self._last_partial = ""
        self._last_audio_buffer: list[bytes] = []

        # Audio preprocessor (VAD + noise reduction + AGC)
        try:
            from modules.audio_preprocessor import AudioPreprocessor
            self._preprocessor = AudioPreprocessor()
        except Exception as e:
            logger.warning(f"Audio preprocessor unavailable: {e}")
            self._preprocessor = None

    # ── Start / Stop ──────────────────────────────────────────

    def start(self):
        """Start the recognition loop in a background thread."""
        self._running = True
        targets = {
            "sr_vosk": self._sr_vosk_loop,
            "raw_vosk": self._raw_vosk_loop,
            "console": self._console_input_loop,
        }
        self._thread = threading.Thread(
            target=targets[self._backend], daemon=True
        )
        self._thread.start()
        logger.info(f"Speech recognizer started (backend={self._backend})")

    def stop(self):
        """Stop the recognition loop and release resources."""
        self._running = False
        # Unblock any thread waiting on _is_speaking
        self._is_speaking.clear()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._backend == "raw_vosk":
            self._close_audio_stream()
        logger.info("Speech recognizer stopped.")

    # ── Properties ────────────────────────────────────────────

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking.is_set()

    @is_speaking.setter
    def is_speaking(self, value: bool):
        if value:
            self._is_speaking.set()
        else:
            self._is_speaking.clear()

    def get_result(self, timeout: float = None) -> Optional[RecognitionResult]:
        """Get the next recognition result from the queue."""
        try:
            return self._result_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ── Recognition mode switching (dual-recognizer) ─────────

    def set_recognition_mode(self, mode: str) -> None:
        """Switch between 'wake' (grammar-constrained) and 'open' (full vocabulary).

        Only effective for the raw_vosk backend; sr_vosk creates one-off
        recognizers per utterance.
        """
        if self._backend != "raw_vosk":
            return
        if mode not in ("wake", "open"):
            logger.warning(f"Unknown recognition mode: {mode!r}")
            return
        if mode == self._recognition_mode:
            return

        self._recognition_mode = mode
        if mode == "wake":
            self._recognizer = self._wake_recognizer
        else:
            self._recognizer = self._open_recognizer

        # Reset the active recognizer state
        self._last_partial = ""
        logger.info(f"Recognition mode switched to: {mode}")

    # ── Grammar re-recognition (two-pass entity extraction) ──

    def recognize_with_grammar(self, grammar: list[str]) -> Optional[RecognitionResult]:
        """Re-recognize the last audio buffer using a grammar-constrained recognizer.

        Args:
            grammar: List of phrases/words to constrain recognition to.

        Returns:
            RecognitionResult if recognition succeeds, None otherwise.
        """
        if not VOSK_AVAILABLE:
            return None

        # Get the audio buffer — available in raw_vosk mode
        audio_buffer = getattr(self, "_last_audio_buffer", [])
        if not audio_buffer:
            logger.debug("No audio buffer available for grammar re-recognition")
            return None

        try:
            grammar_json = json.dumps(grammar + ["[unk]"])
            rec = vosk.KaldiRecognizer(self._model, SAMPLE_RATE, grammar_json)
            rec.SetWords(True)

            for chunk in audio_buffer:
                rec.AcceptWaveform(chunk)

            result = json.loads(rec.FinalResult())
            text = result.get("text", "").strip()

            if text and "[unk]" not in text:
                recognition = RecognitionResult.from_vosk_result(result)
                logger.info(
                    f"Grammar re-recognition: '{text}' (conf={recognition.confidence:.2f})"
                )
                return recognition
        except Exception as e:
            logger.debug(f"Grammar re-recognition failed: {e}")

        return None

    # ── SpeechRecognition + Vosk (offline, proper silence detection) ──

    def _sr_vosk_loop(self):
        """Listen with proper silence detection, recognize with Vosk offline."""
        logger.info("Listening with Vosk (offline, silence-aware)...")

        while self._running:
            # Efficient echo prevention: block until TTS is done
            if self._is_speaking.is_set():
                # Wait efficiently — no busy loop
                while self._is_speaking.is_set() and self._running:
                    # wait() with a timeout so we can check _running periodically
                    self._is_speaking.wait(timeout=0.5)
                    # We want to wait until is_speaking is *cleared*, so
                    # if wait() returned because the event is set, keep going.
                    # If it returned because the event was cleared, break.
                    if not self._is_speaking.is_set():
                        break

                if not self._running:
                    break

                # Drain mic buffer after TTS finishes to prevent echo pickup
                try:
                    with self._sr_mic as source:
                        self._sr_recognizer.adjust_for_ambient_noise(
                            source, duration=POST_TTS_DRAIN_MS / 1000.0
                        )
                except Exception as e:
                    logger.debug(f"Post-TTS mic drain failed: {e}")
                continue

            try:
                with self._sr_mic as source:
                    audio = self._sr_recognizer.listen(
                        source,
                        timeout=STT_LISTEN_TIMEOUT,
                        phrase_time_limit=STT_PHRASE_TIME_LIMIT,
                    )

                # Discard if TTS started while we were listening
                if self._is_speaking.is_set():
                    continue

                # Convert audio to raw data and run through our Vosk model
                raw_data = audio.get_raw_data(
                    convert_rate=SAMPLE_RATE, convert_width=2
                )
                rec = vosk.KaldiRecognizer(self._vosk_model, SAMPLE_RATE)
                rec.SetWords(True)
                rec.AcceptWaveform(raw_data)
                result = json.loads(rec.FinalResult())
                text = result.get("text", "").strip()

                if text:
                    recognition = RecognitionResult.from_vosk_result(result)
                    logger.info(f"Recognized: {text} (conf={recognition.confidence:.2f})")
                    self._enqueue_result(recognition)
                    self._consecutive_errors = 0

            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                logger.debug("Could not understand audio")
                continue
            except Exception as e:
                logger.error(f"Speech recognition error: {e}")
                self._consecutive_errors += 1
                if self._consecutive_errors >= STT_DEVICE_MAX_RETRIES:
                    if not self._reconnect_mic():
                        logger.critical(
                            "Microphone reconnect failed — falling back to console mode"
                        )
                        self._backend = "console"
                        self._console_input_loop()
                        return
                time.sleep(STT_DEVICE_RETRY_INTERVAL)

    def _reconnect_mic(self) -> bool:
        """Attempt to recreate the SpeechRecognition microphone and recalibrate.

        Returns True on success, False on failure.
        """
        logger.warning("Attempting microphone reconnect (sr_vosk)...")
        try:
            self._sr_mic = sr.Microphone(
                device_index=RESPEAKER_DEVICE_INDEX if IS_PI else None,
                sample_rate=SAMPLE_RATE,
            )
            with self._sr_mic as source:
                self._sr_recognizer.adjust_for_ambient_noise(source, duration=1)
            self._consecutive_errors = 0
            logger.info("Microphone reconnected successfully.")
            return True
        except Exception as e:
            logger.error(f"Microphone reconnect failed: {e}")
            return False

    # ── Raw Vosk streaming (for Pi) ──────────────────────────

    def _open_audio_stream(self):
        """Open the PyAudio input stream for raw Vosk."""
        import pyaudio
        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=RESPEAKER_DEVICE_INDEX if IS_PI else None,
            frames_per_buffer=self._chunk_size,
        )
        self._stream.start_stream()

    def _close_audio_stream(self):
        """Safely stop, close the audio stream and terminate PyAudio."""
        try:
            if hasattr(self, "_stream") and self._stream:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None
        except Exception as e:
            logger.debug(f"Error closing audio stream: {e}")
        try:
            if hasattr(self, "_audio") and self._audio:
                self._audio.terminate()
                self._audio = None
        except Exception as e:
            logger.debug(f"Error terminating PyAudio: {e}")

    def _reconnect_stream(self) -> bool:
        """Close and reopen the raw Vosk audio stream.

        Returns True on success, False on failure.
        """
        import pyaudio
        logger.warning("Attempting audio stream reconnect (raw_vosk)...")
        try:
            # Close existing stream
            try:
                if self._stream:
                    self._stream.stop_stream()
                    self._stream.close()
                    self._stream = None
            except Exception:
                pass

            # Terminate and recreate PyAudio
            try:
                if self._audio:
                    self._audio.terminate()
            except Exception:
                pass
            self._audio = pyaudio.PyAudio()

            # Reopen stream
            self._open_audio_stream()

            # Recreate recognizer
            self._recognizer = vosk.KaldiRecognizer(self._model, SAMPLE_RATE)
            self._recognizer.SetWords(True)

            self._consecutive_errors = 0
            self._last_partial = ""
            logger.info("Audio stream reconnected successfully.")
            return True
        except Exception as e:
            logger.error(f"Audio stream reconnect failed: {e}")
            return False

    def _raw_vosk_loop(self):
        """Raw Vosk streaming loop (for Raspberry Pi)."""
        try:
            self._open_audio_stream()
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            logger.critical("Falling back to console mode.")
            self._backend = "console"
            self._console_input_loop()
            return

        # Capture noise profile for preprocessor
        if self._preprocessor is not None:
            try:
                profile_frames = []
                num_frames = int(
                    AUDIO_NOISE_PROFILE_DURATION * SAMPLE_RATE / self._chunk_size
                )
                logger.info("Capturing noise profile for audio preprocessor...")
                for _ in range(max(num_frames, 1)):
                    frame = self._stream.read(
                        self._chunk_size, exception_on_overflow=False
                    )
                    profile_frames.append(frame)
                self._preprocessor.capture_noise_profile(profile_frames)
            except Exception as e:
                logger.warning(f"Noise profile capture failed: {e}")

        logger.info("Vosk listening (raw streaming)...")
        was_speaking = False

        while self._running:
            # Echo prevention: skip processing while TTS is active
            if self._is_speaking.is_set():
                # Read and discard audio data to keep the stream flowing,
                # but do not feed it to the recognizer.
                try:
                    self._stream.read(self._chunk_size, exception_on_overflow=False)
                except Exception:
                    pass
                was_speaking = True
                continue

            # Post-TTS drain: discard buffered audio and reset recognizer
            if was_speaking:
                was_speaking = False
                drain_frames = int(
                    (POST_TTS_DRAIN_MS / 1000.0) * SAMPLE_RATE / self._chunk_size
                )
                for _ in range(max(drain_frames, 1)):
                    try:
                        self._stream.read(
                            self._chunk_size, exception_on_overflow=False
                        )
                    except Exception:
                        break
                # Reset recognizer state (KaldiRecognizer has no Reset method,
                # so recreate it)
                self._recognizer = vosk.KaldiRecognizer(self._model, SAMPLE_RATE)
                self._recognizer.SetWords(True)
                self._last_partial = ""
                continue

            try:
                data = self._stream.read(
                    self._chunk_size, exception_on_overflow=False
                )
            except Exception as e:
                logger.error(f"Audio read error: {e}")
                self._consecutive_errors += 1
                if self._consecutive_errors >= STT_DEVICE_MAX_RETRIES:
                    if not self._reconnect_stream():
                        logger.critical(
                            "Audio stream reconnect failed — falling back to console mode"
                        )
                        self._backend = "console"
                        self._console_input_loop()
                        return
                time.sleep(STT_DEVICE_RETRY_INTERVAL)
                continue

            # Accumulate audio buffer for potential grammar re-recognition
            self._last_audio_buffer.append(data)

            # Audio preprocessing (VAD + noise reduction + AGC)
            if self._preprocessor is not None:
                try:
                    data, is_speech = self._preprocessor.process_frame(data)
                    if not is_speech:
                        # Feed silence to recognizer to maintain timing
                        # (Vosk needs continuous frames for endpoint detection)
                        self._recognizer.AcceptWaveform(data)
                        continue
                except Exception as e:
                    logger.debug(f"Preprocessor error: {e}")

            if self._recognizer.AcceptWaveform(data):
                result_json = self._recognizer.Result()
                result = json.loads(result_json)
                text = result.get("text", "").strip()
                if text:
                    recognition = RecognitionResult.from_vosk_result(result)
                    logger.info(f"Recognized: {text} (conf={recognition.confidence:.2f})")
                    self._enqueue_result(recognition)
                    self._consecutive_errors = 0
                    self._last_partial = ""
                # Clear audio buffer after final result (start fresh for next utterance)
                self._last_audio_buffer = []
            else:
                # Partial result streaming
                if self._on_partial is not None:
                    partial_json = self._recognizer.PartialResult()
                    partial = json.loads(partial_json).get("partial", "").strip()
                    if partial and partial != self._last_partial:
                        self._last_partial = partial
                        try:
                            self._on_partial(partial)
                        except Exception as e:
                            logger.debug(f"on_partial callback error: {e}")

    # ── Console fallback ─────────────────────────────────────

    def _console_input_loop(self):
        """Fallback: read text from console."""
        print("\n[Console Mode] Type your speech input (or 'quit' to exit):")
        while self._running:
            try:
                text = input("[You]: ").strip()
                if text.lower() == "quit":
                    self._running = False
                    break
                if text:
                    result = RecognitionResult(
                        text=text, confidence=1.0, source="console"
                    )
                    self._enqueue_result(result)
            except EOFError:
                break
