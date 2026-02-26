"""
Piper TTS wrapper for offline text-to-speech synthesis.

Non-blocking by default: speak() spawns a daemon thread and returns
immediately. Supports mid-speech interruption via threading.Event with
sub-200ms latency when using Piper streaming mode.

Falls back to macOS 'say' command (via Popen for interruptibility)
or print-only mock mode when Piper is unavailable.
"""
import io
import logging
import platform
import subprocess
import threading
import wave
from typing import Callable, Optional

from config import (
    PIPER_MODEL_PATH,
    PIPER_CONFIG_PATH,
    TTS_SAMPLE_RATE,
    TTS_OUTPUT_DEVICE_INDEX,
    MACOS_TTS_VOICE,
)

logger = logging.getLogger(__name__)

# ── Optional dependency probing ──────────────────────────────
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logger.warning("Piper TTS not available.")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

# Check if macOS 'say' command is available as fallback
MACOS_SAY_AVAILABLE = platform.system() == "Darwin"


class TextToSpeech:
    """
    Synthesize speech from text using Piper TTS.

    Falls back to macOS 'say' command, then to print-only mode.
    Sets a shared ``is_speaking`` flag for echo prevention in the STT
    module.

    Parameters
    ----------
    is_speaking_event : threading.Event
        Shared event that is *set* while audio is playing so the speech
        recognizer can ignore mic input (echo prevention).
    """

    def __init__(self, is_speaking_event: threading.Event):
        self.is_mock: bool = not PIPER_AVAILABLE
        self._use_macos_say: bool = self.is_mock and MACOS_SAY_AVAILABLE
        self._is_speaking: threading.Event = is_speaking_event

        self._voice: Optional["PiperVoice"] = None
        self._audio = None  # pyaudio.PyAudio instance (or None)

        self._playback_lock = threading.Lock()
        self._interrupt = threading.Event()
        self._speak_thread: Optional[threading.Thread] = None
        self._has_streaming: bool = False
        self._macos_process: Optional[subprocess.Popen] = None

        # ── Load Piper model ─────────────────────────────────────
        if not self.is_mock:
            try:
                logger.info("Loading Piper model: %s", PIPER_MODEL_PATH)
                self._voice = PiperVoice.load(
                    PIPER_MODEL_PATH,
                    config_path=PIPER_CONFIG_PATH,
                )
                logger.info("Piper TTS model loaded successfully.")

                # Check for streaming support
                if hasattr(self._voice, "synthesize_stream_raw"):
                    self._has_streaming = True
                    logger.info("Piper streaming synthesis available.")
                else:
                    logger.warning(
                        "Piper version does not support synthesize_stream_raw; "
                        "falling back to buffered synthesis."
                    )

                # Validate sample rate
                try:
                    model_rate = self._voice.config.sample_rate
                    if model_rate != TTS_SAMPLE_RATE:
                        logger.warning(
                            "Piper model sample rate (%d) differs from "
                            "TTS_SAMPLE_RATE config (%d). Using model rate.",
                            model_rate,
                            TTS_SAMPLE_RATE,
                        )
                except AttributeError:
                    logger.debug("Could not read sample rate from Piper config.")

            except Exception as e:
                logger.error("Failed to load Piper model: %s", e)
                self.is_mock = True
                self._use_macos_say = MACOS_SAY_AVAILABLE

        # ── Initialise PyAudio ───────────────────────────────────
        if PYAUDIO_AVAILABLE and not self.is_mock:
            try:
                self._audio = pyaudio.PyAudio()
            except Exception as e:
                logger.error("Failed to initialise PyAudio: %s", e)

        if self._use_macos_say:
            logger.info(
                "Using macOS 'say' command for TTS (voice=%s).",
                MACOS_TTS_VOICE,
            )

    # ──────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────

    def speak(
        self,
        text: str,
        on_complete: Optional[Callable[[bool], None]] = None,
        blocking: bool = False,
    ) -> None:
        """Synthesize and play *text*.

        Parameters
        ----------
        text : str
            The text to speak.
        on_complete : callable, optional
            Called with ``True`` if speech finished naturally, or ``False``
            if it was interrupted.
        blocking : bool
            When *False* (the default), synthesis + playback runs on a
            daemon thread and this method returns immediately.  When
            *True*, behaves synchronously (blocks until playback ends).
        """
        if not text or not text.strip():
            if on_complete:
                on_complete(True)
            return

        self._interrupt.clear()

        if blocking:
            self._do_speak(text, on_complete)
        else:
            self._speak_thread = threading.Thread(
                target=self._do_speak,
                args=(text, on_complete),
                daemon=True,
            )
            self._speak_thread.start()

    def interrupt(self) -> None:
        """Interrupt the current speech playback.

        The streaming loop checks the interrupt event between audio
        chunks, giving sub-200 ms reaction time.  For macOS ``say``,
        the child process is terminated immediately.
        """
        self._interrupt.set()

        # Kill macOS say process if running
        proc = self._macos_process
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    def close(self) -> None:
        """Release audio resources.

        Interrupts any in-flight speech, waits briefly for the playback
        thread to finish, then terminates PyAudio.
        """
        self.interrupt()

        thread = self._speak_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        if self._audio is not None:
            try:
                self._audio.terminate()
            except Exception:
                pass
            self._audio = None

    # ──────────────────────────────────────────────────────────────
    #  Internal routing
    # ──────────────────────────────────────────────────────────────

    def _do_speak(
        self,
        text: str,
        on_complete: Optional[Callable[[bool], None]],
    ) -> None:
        """Route to the appropriate backend and invoke *on_complete*."""
        completed_naturally = False
        try:
            if not self.is_mock:
                completed_naturally = self._piper_speak(text)
            elif self._use_macos_say:
                completed_naturally = self._macos_speak(text)
            else:
                completed_naturally = self._mock_speak(text)
        except Exception as e:
            logger.error("TTS error: %s", e, exc_info=True)
            completed_naturally = False
        finally:
            if on_complete is not None:
                try:
                    on_complete(completed_naturally)
                except Exception as cb_err:
                    logger.error("on_complete callback error: %s", cb_err)

    # ──────────────────────────────────────────────────────────────
    #  Piper backend
    # ──────────────────────────────────────────────────────────────

    def _piper_speak(self, text: str) -> bool:
        """Synthesize with Piper and play via PyAudio.

        Returns ``True`` if playback completed naturally, ``False`` if
        interrupted or an error occurred.
        """
        if self._has_streaming:
            return self._piper_speak_streaming(text)
        return self._piper_speak_buffered(text)

    def _piper_speak_streaming(self, text: str) -> bool:
        """Stream Piper audio chunks directly to PyAudio.

        Opens the output stream once, then writes int16 chunks as they
        arrive from ``synthesize_stream_raw``.  Checks the interrupt
        event between chunks for fast cancellation.
        """
        self._is_speaking.set()
        stream = None
        try:
            # Determine sample rate from model config
            try:
                sample_rate = self._voice.config.sample_rate
            except AttributeError:
                sample_rate = TTS_SAMPLE_RATE

            # Build PyAudio stream kwargs
            stream_kwargs = dict(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                output=True,
            )
            if TTS_OUTPUT_DEVICE_INDEX is not None:
                stream_kwargs["output_device_index"] = TTS_OUTPUT_DEVICE_INDEX

            with self._playback_lock:
                stream = self._audio.open(**stream_kwargs)

            for audio_chunk in self._voice.synthesize_stream_raw(text):
                if self._interrupt.is_set():
                    logger.info("Speech interrupted (streaming).")
                    return False
                stream.write(audio_chunk)

            return True

        except Exception as e:
            logger.error("Piper streaming playback error: %s", e)
            return False
        finally:
            if stream is not None:
                try:
                    with self._playback_lock:
                        stream.stop_stream()
                        stream.close()
                except Exception:
                    pass
            self._is_speaking.clear()

    def _piper_speak_buffered(self, text: str) -> bool:
        """Fallback: synthesize full WAV buffer then play with interrupt checks.

        Used when the installed Piper version does not expose
        ``synthesize_stream_raw``.
        """
        self._is_speaking.set()
        stream = None
        try:
            # Synthesize entire utterance into an in-memory WAV
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file)

            if self._interrupt.is_set():
                return False

            wav_buffer.seek(0)
            with wave.open(wav_buffer, "rb") as wav_file:
                fmt = self._audio.get_format_from_width(wav_file.getsampwidth())
                channels = wav_file.getnchannels()
                rate = wav_file.getframerate()

                stream_kwargs = dict(
                    format=fmt,
                    channels=channels,
                    rate=rate,
                    output=True,
                )
                if TTS_OUTPUT_DEVICE_INDEX is not None:
                    stream_kwargs["output_device_index"] = TTS_OUTPUT_DEVICE_INDEX

                with self._playback_lock:
                    stream = self._audio.open(**stream_kwargs)

                chunk_size = 1024
                data = wav_file.readframes(chunk_size)
                while data:
                    if self._interrupt.is_set():
                        logger.info("Speech interrupted (buffered).")
                        return False
                    stream.write(data)
                    data = wav_file.readframes(chunk_size)

            return True

        except Exception as e:
            logger.error("TTS buffered playback error: %s", e)
            return False
        finally:
            if stream is not None:
                try:
                    with self._playback_lock:
                        stream.stop_stream()
                        stream.close()
                except Exception:
                    pass
            self._is_speaking.clear()

    # ──────────────────────────────────────────────────────────────
    #  macOS fallback
    # ──────────────────────────────────────────────────────────────

    def _macos_speak(self, text: str) -> bool:
        """Use macOS ``say`` via :class:`subprocess.Popen` for interruptibility.

        Returns ``True`` on natural completion, ``False`` if interrupted.
        """
        self._is_speaking.set()
        try:
            print(f"[Robot]: {text}")
            self._macos_process = subprocess.Popen(
                ["say", "-v", MACOS_TTS_VOICE, "-r", "180", text],
            )
            # Poll until done or interrupted
            while self._macos_process.poll() is None:
                if self._interrupt.is_set():
                    logger.info("Speech interrupted (macOS say).")
                    try:
                        self._macos_process.terminate()
                        self._macos_process.wait(timeout=2.0)
                    except Exception:
                        pass
                    return False
                # Small sleep to avoid busy-waiting
                self._interrupt.wait(timeout=0.1)

            return self._macos_process.returncode == 0

        except Exception as e:
            logger.error("macOS say error: %s", e)
            return False
        finally:
            self._macos_process = None
            self._is_speaking.clear()

    # ──────────────────────────────────────────────────────────────
    #  Mock fallback
    # ──────────────────────────────────────────────────────────────

    def _mock_speak(self, text: str) -> bool:
        """Print text to console as a fallback.

        Returns ``True`` (always completes naturally).
        """
        self._is_speaking.set()
        try:
            print(f"[ROBOT SAYS]: {text}")
            return True
        finally:
            self._is_speaking.clear()
