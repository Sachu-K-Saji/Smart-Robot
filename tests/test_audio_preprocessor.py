"""Tests for the audio preprocessing pipeline."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.audio_preprocessor import AudioPreprocessor, WEBRTCVAD_AVAILABLE


class TestAudioPreprocessor:
    """Test AudioPreprocessor VAD, noise reduction, and AGC."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create preprocessor with all features enabled."""
        self.preprocessor = AudioPreprocessor()

    @staticmethod
    def _make_silence(num_samples: int = 4000) -> bytes:
        """Generate silent (zero-valued) PCM int16 frames."""
        return b"\x00\x00" * num_samples

    @staticmethod
    def _make_sine_wave(
        freq: float = 440.0,
        num_samples: int = 4000,
        amplitude: int = 10000,
        sample_rate: int = 16000,
    ) -> bytes:
        """Generate a sine wave as PCM int16 bytes."""
        t = np.arange(num_samples) / sample_rate
        wave = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.int16)
        return wave.tobytes()

    @staticmethod
    def _make_quiet_audio(num_samples: int = 4000) -> bytes:
        """Generate very quiet audio (low RMS)."""
        rng = np.random.default_rng(42)
        wave = rng.integers(-50, 50, num_samples, dtype=np.int16)
        return wave.tobytes()

    @staticmethod
    def _make_loud_audio(num_samples: int = 4000) -> bytes:
        """Generate loud audio (high RMS)."""
        rng = np.random.default_rng(42)
        wave = rng.integers(-30000, 30000, num_samples, dtype=np.int16)
        return wave.tobytes()

    def test_passthrough_when_disabled(self):
        """When all flags are disabled, audio passes through unchanged."""
        pp = AudioPreprocessor(
            vad_enabled=False,
            noise_reduce_enabled=False,
            agc_enabled=False,
        )

        raw = self._make_sine_wave()
        processed, is_speech = pp.process_frame(raw)
        assert is_speech is True  # VAD disabled → always speech
        # Audio should be unchanged (just float32 round-trip)
        orig_arr = np.frombuffer(raw, dtype=np.int16)
        proc_arr = np.frombuffer(processed, dtype=np.int16)
        np.testing.assert_array_equal(orig_arr, proc_arr)

    @pytest.mark.skipif(not WEBRTCVAD_AVAILABLE, reason="webrtcvad not installed")
    def test_vad_detects_silence(self):
        """VAD should classify zero-frames as non-speech."""
        silence = self._make_silence(4000)
        _, is_speech = self.preprocessor.process_frame(silence)
        assert is_speech is False

    @pytest.mark.skipif(not WEBRTCVAD_AVAILABLE, reason="webrtcvad not installed")
    def test_vad_detects_speech(self):
        """VAD should classify a sine wave as speech."""
        speech = self._make_sine_wave(freq=300, amplitude=15000)
        _, is_speech = self.preprocessor.process_frame(speech)
        assert is_speech is True

    def test_agc_boosts_quiet_audio(self):
        """AGC should increase the RMS of quiet audio."""
        # Disable noise reduction to isolate AGC behavior
        pp = AudioPreprocessor(
            vad_enabled=False,
            noise_reduce_enabled=False,
            agc_enabled=True,
        )

        quiet = self._make_quiet_audio()
        processed, _ = pp.process_frame(quiet)

        orig_rms = np.sqrt(np.mean(
            np.frombuffer(quiet, dtype=np.int16).astype(np.float32) ** 2
        ))
        proc_rms = np.sqrt(np.mean(
            np.frombuffer(processed, dtype=np.int16).astype(np.float32) ** 2
        ))
        # Processed should be louder (boosted by AGC)
        assert proc_rms >= orig_rms

    def test_agc_attenuates_loud_audio(self):
        """AGC should decrease the RMS of very loud audio."""
        # Disable noise reduction to isolate AGC behavior
        pp = AudioPreprocessor(
            vad_enabled=False,
            noise_reduce_enabled=False,
            agc_enabled=True,
        )

        loud = self._make_loud_audio()
        processed, _ = pp.process_frame(loud)

        orig_rms = np.sqrt(np.mean(
            np.frombuffer(loud, dtype=np.int16).astype(np.float32) ** 2
        ))
        proc_rms = np.sqrt(np.mean(
            np.frombuffer(processed, dtype=np.int16).astype(np.float32) ** 2
        ))
        # Processed should be quieter (attenuated toward target)
        assert proc_rms <= orig_rms

    def test_noise_profile_capture(self):
        """capture_noise_profile should store a numpy array."""
        frames = [self._make_silence(4000) for _ in range(4)]
        self.preprocessor.capture_noise_profile(frames)
        assert self.preprocessor._noise_profile is not None
        assert len(self.preprocessor._noise_profile) == 4000 * 4

    def test_noise_profile_empty(self):
        """Empty frames list should not crash."""
        self.preprocessor.capture_noise_profile([])
        assert self.preprocessor._noise_profile is None

    def test_output_is_valid_int16(self):
        """Processed output should be valid int16 PCM bytes."""
        pp = AudioPreprocessor(
            vad_enabled=False,
            noise_reduce_enabled=False,
            agc_enabled=True,
        )
        raw = self._make_sine_wave(amplitude=20000)
        processed, _ = pp.process_frame(raw)

        # Should be parseable as int16
        arr = np.frombuffer(processed, dtype=np.int16)
        assert arr.dtype == np.int16
        assert len(arr) == 4000  # same number of samples
