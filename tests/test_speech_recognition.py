"""Tests for speech recognition module — RecognitionResult and confidence scoring."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.speech_recognition import RecognitionResult


class TestRecognitionResult:
    """Test RecognitionResult dataclass behavior."""

    def test_str_returns_text(self):
        r = RecognitionResult(text="hello world", confidence=0.95)
        assert str(r) == "hello world"

    def test_eq_with_string(self):
        r = RecognitionResult(text="hello", confidence=0.9)
        assert r == "hello"
        assert r != "goodbye"

    def test_eq_with_result(self):
        r1 = RecognitionResult(text="hello", confidence=0.9)
        r2 = RecognitionResult(text="hello", confidence=0.5)
        assert r1 == r2  # equality is text-based

    def test_hash_matches_string(self):
        r = RecognitionResult(text="hello", confidence=0.9)
        assert hash(r) == hash("hello")

    def test_default_values(self):
        r = RecognitionResult(text="test")
        assert r.confidence == 1.0
        assert r.word_confidences == []
        assert r.is_final is True
        assert r.source == "vosk"

    def test_from_vosk_result_with_words(self):
        """Extract word-level confidences from Vosk JSON format."""
        vosk_result = {
            "result": [
                {"conf": 0.95, "word": "hey", "start": 0.0, "end": 0.3},
                {"conf": 0.87, "word": "robot", "start": 0.3, "end": 0.8},
            ],
            "text": "hey robot",
        }
        r = RecognitionResult.from_vosk_result(vosk_result)
        assert r.text == "hey robot"
        assert r.confidence == pytest.approx(0.91, abs=0.01)
        assert len(r.word_confidences) == 2
        assert r.word_confidences[0]["word"] == "hey"
        assert r.word_confidences[1]["conf"] == 0.87
        assert r.source == "vosk"

    def test_from_vosk_result_no_words(self):
        """Vosk result without word-level data should have 0.0 confidence."""
        vosk_result = {"text": "hey robot"}
        r = RecognitionResult.from_vosk_result(vosk_result)
        assert r.text == "hey robot"
        assert r.confidence == 0.0
        assert r.word_confidences == []

    def test_from_vosk_result_empty(self):
        vosk_result = {"text": ""}
        r = RecognitionResult.from_vosk_result(vosk_result)
        assert r.text == ""
        assert r.confidence == 0.0

    def test_console_source(self):
        r = RecognitionResult(text="typed input", confidence=1.0, source="console")
        assert r.source == "console"
        assert r.confidence == 1.0

    def test_string_operations_work(self):
        """RecognitionResult should work with common string operations via str()."""
        r = RecognitionResult(text="Hey Robot", confidence=0.9)
        assert str(r).lower() == "hey robot"
        assert str(r).split() == ["Hey", "Robot"]
        assert f"You said: {r}" == "You said: Hey Robot"
