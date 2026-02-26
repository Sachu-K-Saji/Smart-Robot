"""Tests for the state machine and main loop hardening."""
import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRobotStateMachine:
    """Test state machine transitions and error recovery."""

    @pytest.fixture(autouse=True)
    def setup_robot(self):
        """Create a CampusRobot with mocked subsystems."""
        with patch("main.CampusDatabase") as MockDB, \
             patch("main.CampusNavigator") as MockNav, \
             patch("main.SpeechRecognizer") as MockSTT, \
             patch("main.TextToSpeech") as MockTTS, \
             patch("main.EyeDisplay") as MockDisplay, \
             patch("main.VideoPlayer") as MockVideo, \
             patch("main.PowerMonitor") as MockPower:

            # Configure mocks
            MockDB.return_value.get_all_location_names.return_value = ["Library"]
            MockDB.return_value.get_all_faculty_names.return_value = ["Dr. Test"]
            MockDB.return_value.get_all_department_names.return_value = ["CS"]

            mock_display = MockDisplay.return_value
            mock_display.expression = None

            from main import CampusRobot
            self.robot = CampusRobot()
            self.sm = self.robot.state_machine
            yield

    def test_initial_state_is_idle(self):
        assert self.sm.current_state == self.sm.idle

    def test_normal_flow(self):
        """idle -> listening -> processing -> responding -> idle"""
        self.sm.wake_up()
        assert self.sm.current_state == self.sm.listening

        self.sm.hear_input()
        assert self.sm.current_state == self.sm.processing

        self.sm.generate_response()
        assert self.sm.current_state == self.sm.responding

        self.sm.finish_response()
        assert self.sm.current_state == self.sm.idle

    def test_error_from_listening(self):
        self.sm.wake_up()
        assert self.sm.current_state == self.sm.listening
        self.sm.error()
        assert self.sm.current_state == self.sm.idle

    def test_error_from_processing(self):
        self.sm.wake_up()
        self.sm.hear_input()
        assert self.sm.current_state == self.sm.processing
        self.sm.error()
        assert self.sm.current_state == self.sm.idle

    def test_error_from_responding(self):
        self.sm.wake_up()
        self.sm.hear_input()
        self.sm.generate_response()
        assert self.sm.current_state == self.sm.responding
        self.sm.error()
        assert self.sm.current_state == self.sm.idle

    def test_safe_transition_success(self):
        result = self.robot._safe_transition("wake_up")
        assert result is True
        assert self.sm.current_state == self.sm.listening

    def test_safe_transition_failure(self):
        """Trying an invalid transition should return False, not crash."""
        # Can't hear_input from idle
        result = self.robot._safe_transition("hear_input")
        assert result is False
        assert self.sm.current_state == self.sm.idle

    def test_force_idle_from_listening(self):
        self.sm.wake_up()
        assert self.sm.current_state == self.sm.listening
        self.robot._force_idle()
        assert self.sm.current_state == self.sm.idle

    def test_force_idle_from_processing(self):
        self.sm.wake_up()
        self.sm.hear_input()
        assert self.sm.current_state == self.sm.processing
        self.robot._force_idle()
        assert self.sm.current_state == self.sm.idle

    def test_force_idle_already_idle(self):
        """force_idle from idle should not crash."""
        self.robot._force_idle()
        assert self.sm.current_state == self.sm.idle

    def test_is_awake_thread_safe(self):
        """is_awake property should be safe from multiple threads."""
        results = []

        def toggle():
            for _ in range(100):
                self.robot.is_awake = True
                results.append(self.robot.is_awake)
                self.robot.is_awake = False
                results.append(self.robot.is_awake)

        threads = [threading.Thread(target=toggle) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors; values should be booleans
        assert all(isinstance(r, bool) for r in results)


class TestWakeWordMatching:
    """Test the multi-layer wake word validation."""

    @pytest.fixture(autouse=True)
    def setup_robot(self):
        with patch("main.CampusDatabase") as MockDB, \
             patch("main.CampusNavigator"), \
             patch("main.SpeechRecognizer"), \
             patch("main.TextToSpeech"), \
             patch("main.EyeDisplay"), \
             patch("main.VideoPlayer"), \
             patch("main.PowerMonitor"):

            MockDB.return_value.get_all_location_names.return_value = []
            MockDB.return_value.get_all_faculty_names.return_value = []
            MockDB.return_value.get_all_department_names.return_value = []

            from main import CampusRobot
            self.robot = CampusRobot()
            yield

    def test_exact_match(self):
        assert self.robot._matches_wake_word("hey robot") is True

    def test_exact_match_in_sentence(self):
        assert self.robot._matches_wake_word("okay hey robot tell me something") is True

    def test_fuzzy_match_typo(self):
        assert self.robot._matches_wake_word("hey robat") is True

    def test_too_short_input(self):
        """Single word can't match 'hey robot'."""
        assert self.robot._matches_wake_word("hey") is False

    def test_completely_unrelated(self):
        assert self.robot._matches_wake_word("what time is it") is False

    def test_case_insensitive(self):
        assert self.robot._matches_wake_word("HEY ROBOT") is True

    # ── Indian accent wake word variants (Phase 4) ────────────

    def test_variant_hey_robat(self):
        assert self.robot._matches_wake_word("hey robat") is True

    def test_variant_hay_robot(self):
        assert self.robot._matches_wake_word("hay robot") is True

    def test_variant_hey_robert(self):
        assert self.robot._matches_wake_word("hey robert") is True

    def test_variant_hey_robo(self):
        assert self.robot._matches_wake_word("hey robo") is True

    def test_variant_hai_robot(self):
        assert self.robot._matches_wake_word("hai robot") is True

    def test_variant_he_robot(self):
        assert self.robot._matches_wake_word("he robot") is True

    def test_variant_in_sentence(self):
        """Variant embedded in a longer sentence should still match."""
        assert self.robot._matches_wake_word("okay hay robot tell me about library") is True

    def test_unrelated_still_rejected(self):
        """Random phrases should not match even with variant checking."""
        assert self.robot._matches_wake_word("play some music please") is False

    def test_single_word_still_rejected(self):
        """Single word should not match two-word wake phrase."""
        assert self.robot._matches_wake_word("robot") is False
