"""
Audio preprocessing pipeline for speech recognition.

Pipeline: raw audio → VAD gate → noise reduction → gain normalization → output

Each stage can be independently enabled/disabled via config flags.
All processing uses numpy float32 for Pi performance.
"""
import logging

import numpy as np

from config import (
    SAMPLE_RATE,
    AUDIO_VAD_ENABLED,
    AUDIO_VAD_AGGRESSIVENESS,
    AUDIO_NOISE_REDUCE_ENABLED,
    AUDIO_NOISE_REDUCE_STATIONARY,
    AUDIO_AGC_ENABLED,
    AUDIO_AGC_TARGET_RMS,
    AUDIO_AGC_MAX_GAIN,
    AUDIO_AGC_MIN_GAIN,
    AUDIO_VAD_SPEECH_FRAME_RATIO,
)

logger = logging.getLogger(__name__)

# Optional dependencies — degrade gracefully
try:
    import webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False
    logger.info("webrtcvad not installed — VAD disabled")

try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    NOISEREDUCE_AVAILABLE = False
    logger.info("noisereduce not installed — noise reduction disabled")


class AudioPreprocessor:
    """Audio preprocessing pipeline: VAD + noise reduction + AGC.

    Each stage is independently toggleable via constructor flags
    (defaulting to config values).
    """

    # WebRTC VAD requires 10, 20, or 30ms frames at 16kHz
    VAD_FRAME_DURATION_MS = 30
    VAD_FRAME_SAMPLES = SAMPLE_RATE * VAD_FRAME_DURATION_MS // 1000  # 480 at 16kHz

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        vad_enabled: bool = AUDIO_VAD_ENABLED,
        noise_reduce_enabled: bool = AUDIO_NOISE_REDUCE_ENABLED,
        agc_enabled: bool = AUDIO_AGC_ENABLED,
    ):
        self._sample_rate = sample_rate
        self._noise_profile: np.ndarray | None = None
        self.noise_reduce_enabled = noise_reduce_enabled
        self.agc_enabled = agc_enabled

        # Instance-level AGC parameters (from config defaults)
        self.agc_target_rms = AUDIO_AGC_TARGET_RMS
        self.agc_max_gain = AUDIO_AGC_MAX_GAIN
        self.agc_min_gain = AUDIO_AGC_MIN_GAIN

        # Initialize VAD
        self._vad = None
        if vad_enabled and WEBRTCVAD_AVAILABLE:
            self._vad = webrtcvad.Vad(AUDIO_VAD_AGGRESSIVENESS)
            logger.info(f"WebRTC VAD enabled (aggressiveness={AUDIO_VAD_AGGRESSIVENESS})")

    def capture_noise_profile(self, audio_frames: list[bytes]) -> None:
        """Capture a noise profile from ambient audio frames.

        Call during microphone calibration at startup. The frames
        should represent silence/ambient noise only.
        """
        if not audio_frames:
            return
        raw = b"".join(audio_frames)
        self._noise_profile = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        logger.info(
            f"Noise profile captured: {len(self._noise_profile)} samples "
            f"({len(self._noise_profile) / self._sample_rate:.1f}s)"
        )

    def process_frame(self, raw_frame: bytes) -> tuple[bytes, bool]:
        """Process a single audio frame through the pipeline.

        Args:
            raw_frame: Raw int16 PCM audio bytes.

        Returns:
            (processed_frame, is_speech) — processed audio bytes and
            whether the frame contains speech.
        """
        # Convert to float32 for processing
        samples = np.frombuffer(raw_frame, dtype=np.int16).astype(np.float32)

        # Stage 1: VAD
        is_speech = self._detect_speech(raw_frame)

        # Stage 2: Noise reduction (only on speech frames to save CPU)
        if is_speech:
            samples = self._reduce_noise(samples)

        # Stage 3: AGC
        if is_speech:
            samples = self._apply_agc(samples)

        # Convert back to int16 bytes
        samples = np.clip(samples, -32768, 32767).astype(np.int16)
        return samples.tobytes(), is_speech

    def _detect_speech(self, raw_frame: bytes) -> bool:
        """Detect speech using WebRTC VAD on 30ms sub-frames.

        Returns True if the fraction of speech sub-frames exceeds
        the configured threshold.
        """
        if self._vad is None:
            return True  # VAD disabled — assume all frames are speech

        frame_bytes = self.VAD_FRAME_SAMPLES * 2  # 2 bytes per int16 sample
        total_subframes = 0
        speech_subframes = 0

        for offset in range(0, len(raw_frame) - frame_bytes + 1, frame_bytes):
            subframe = raw_frame[offset:offset + frame_bytes]
            if len(subframe) < frame_bytes:
                break
            total_subframes += 1
            try:
                if self._vad.is_speech(subframe, self._sample_rate):
                    speech_subframes += 1
            except Exception:
                # Invalid frame size or rate — treat as speech
                return True

        if total_subframes == 0:
            return True

        ratio = speech_subframes / total_subframes
        return ratio >= AUDIO_VAD_SPEECH_FRAME_RATIO

    def _reduce_noise(self, samples: np.ndarray) -> np.ndarray:
        """Apply noise reduction using noisereduce library."""
        if not self.noise_reduce_enabled or not NOISEREDUCE_AVAILABLE:
            return samples

        try:
            reduced = nr.reduce_noise(
                y=samples,
                sr=self._sample_rate,
                y_noise=self._noise_profile,
                stationary=AUDIO_NOISE_REDUCE_STATIONARY,
            )
            return reduced.astype(np.float32)
        except Exception as e:
            logger.debug(f"Noise reduction failed: {e}")
            return samples

    def _apply_agc(self, samples: np.ndarray) -> np.ndarray:
        """Apply automatic gain control (RMS-based)."""
        if not self.agc_enabled:
            return samples

        rms = np.sqrt(np.mean(samples ** 2))
        if rms < 1.0:
            return samples  # near-silence, don't amplify

        desired_gain = self.agc_target_rms / rms
        gain = np.clip(desired_gain, self.agc_min_gain, self.agc_max_gain)
        return samples * gain
