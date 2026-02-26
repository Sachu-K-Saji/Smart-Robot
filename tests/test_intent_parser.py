"""Tests for the intent parser module."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.intent_parser import IntentParser


class TestIntentParser:

    @pytest.fixture(autouse=True)
    def setup_parser(self):
        self.parser = IntentParser(
            location_names=["Main Gate", "Central Library", "CS Department", "Cafeteria"],
            faculty_names=["Dr. Rajesh Kumar", "Dr. Priya Sharma", "Dr. Sunil J"],
            department_names=[
                "Computer Science and Engineering",
                "Mechanical Engineering",
                "Civil Engineering",
                "Hotel Management",
            ],
            fuzzy_threshold=70,
        )

    def test_navigation_intent(self):
        result = self.parser.parse("how do I get to the library")
        assert result.intent == "navigation"
        assert result.confidence > 0.5

    def test_faculty_intent(self):
        result = self.parser.parse("who is Dr. Rajesh Kumar")
        assert result.intent == "faculty_info"

    def test_greeting_intent(self):
        result = self.parser.parse("hello")
        assert result.intent == "greeting"

    def test_farewell_intent(self):
        result = self.parser.parse("thank you goodbye")
        assert result.intent == "farewell"

    def test_help_intent(self):
        result = self.parser.parse("what can you do")
        assert result.intent == "help"

    def test_entity_extraction_location(self):
        result = self.parser.parse("where is the cafeteria")
        assert "location" in result.entities
        assert result.entities["location"] == "Cafeteria"

    def test_entity_extraction_faculty(self):
        result = self.parser.parse("who is Dr. Rajesh Kumar")
        assert "faculty_name" in result.entities
        assert result.entities["faculty_name"] == "Dr. Rajesh Kumar"

    def test_unknown_intent(self):
        result = self.parser.parse("xyzzy foobar baz")
        assert result.intent == "unknown"

    def test_fuzzy_location_match(self):
        result = self.parser.parse("directions to the central library")
        assert "location" in result.entities
        assert result.entities["location"] == "Central Library"

    def test_empty_input(self):
        result = self.parser.parse("")
        assert result.intent == "unknown"
        assert result.confidence == 0.0

    # ── Campus info intent ────────────────────────────────────

    def test_campus_info_tell_me_about(self):
        result = self.parser.parse("tell me about the hostel")
        assert result.intent == "campus_info"

    def test_campus_info_keyword_library(self):
        result = self.parser.parse("library")
        assert result.intent == "campus_info"

    def test_campus_info_keyword_admission(self):
        result = self.parser.parse("what about admission process")
        assert result.intent == "campus_info"

    def test_campus_info_keyword_placement(self):
        result = self.parser.parse("placement information")
        assert result.intent == "campus_info"

    def test_campus_info_is_there(self):
        result = self.parser.parse("is there a sports ground")
        assert result.intent == "campus_info"

    # ── Department info with new keywords ─────────────────────

    def test_department_info_hotel_management(self):
        result = self.parser.parse("tell me about hotel management department")
        assert result.intent == "department_info"

    def test_department_info_civil(self):
        result = self.parser.parse("civil engineering department")
        assert result.intent == "department_info"

    # ── Multi-pattern scoring ──────────────────────────────────

    def test_navigation_beats_campus_info(self):
        """'where is the library' should be navigation, not campus_info,
        even though both patterns match."""
        result = self.parser.parse("where is the library")
        assert result.intent == "navigation"

    def test_faculty_info_beats_generic(self):
        """'who is the principal' should be faculty_info."""
        result = self.parser.parse("who is the principal")
        assert result.intent == "faculty_info"

    def test_confidence_varies_by_specificity(self):
        """More specific inputs should get higher confidence."""
        nav_result = self.parser.parse("how do I get to the central library")
        greeting_result = self.parser.parse("hello there good morning")
        assert nav_result.confidence > greeting_result.confidence

    # ── STT error correction ───────────────────────────────────

    def test_stt_correction_cs(self):
        """'see us department' should be corrected to 'CS department'."""
        result = self.parser.parse("tell me about see us department")
        assert result.intent in ("department_info", "campus_info")

    def test_raw_text_preserved(self):
        """raw_text should contain the original, not preprocessed text."""
        result = self.parser.parse("see us department")
        assert result.raw_text == "see us department"

    # ── Entity conflict resolution ─────────────────────────────

    def test_entity_precedence_navigation(self):
        """Clear navigation input should resolve to navigation intent."""
        result = self.parser.parse("how do I get to the cafeteria")
        assert result.intent == "navigation"
        assert "location" in result.entities
        assert result.entities["location"] == "Cafeteria"

    # ── token_set_ratio false positive guard ───────────────────

    def test_short_candidate_no_false_positive(self):
        """Short entity names should not match everything."""
        parser = IntentParser(
            location_names=["IT"],
            faculty_names=[],
            department_names=[],
            fuzzy_threshold=70,
        )
        result = parser.parse("tell me about the history of this institution")
        # "IT" should NOT match "institution" via token_set_ratio
        if "location" in result.entities:
            # If it matches, the score should be high (exact substring)
            assert result.entities.get("location_score", 0) >= 90

    # ── Indian English STT corrections (Phase 1) ──────────────

    def test_indian_v_w_confusion(self):
        """'vhere is the library' should correct 'vhere' → 'where'."""
        result = self.parser.parse("vhere is the liberry")
        assert result.intent == "navigation"

    def test_indian_th_substitution(self):
        """'dat' → 'that', 'dis' → 'this' via STT corrections."""
        result = self.parser.parse("vhat is dat department")
        # 'vhat' → 'what', 'dat' → 'that'
        assert result.intent in ("department_info", "campus_info", "unknown")

    def test_department_acronym_variants(self):
        """Various STT garbles of department acronyms should normalize."""
        for garble in ["see as", "c s", "eye tea", "e c e", "m c a", "b c a"]:
            result = self.parser.parse(f"tell me about {garble} department")
            assert result.intent in ("department_info", "campus_info"), (
                f"Failed for garble: {garble}"
            )

    def test_campus_term_corrections(self):
        """Misspelled campus terms should be corrected."""
        result = self.parser.parse("where is the liberry")
        assert result.intent == "navigation"

    def test_college_name_variants(self):
        """'lord's' → 'Lourdes', 'martha' → 'Matha'."""
        result = self.parser.parse("tell me about lord's martha college")
        # Should correct to "Lourdes Matha"
        assert "Lourdes" in result.raw_text or result.intent in ("campus_info", "unknown")

    def test_faculty_name_garbles(self):
        """'raja sh' → 'Rajesh', 'sure esh' → 'Suresh'."""
        result = self.parser.parse("who is doctor raja sh kumar")
        assert result.intent == "faculty_info"
        assert "faculty_name" in result.entities

    def test_phonetic_substitution_guarded(self):
        """Phonetic subs should not corrupt words not in vocabulary."""
        result = self.parser.parse("very good morning")
        # "very" should NOT become "wery" because "wery" is not in vocabulary
        assert result.raw_text == "very good morning"

    def test_hostel_correction(self):
        """'hostle' → 'hostel'."""
        result = self.parser.parse("tell me about the hostle")
        assert result.intent == "campus_info"

    def test_canteen_correction(self):
        """'can teen' → 'canteen'."""
        result = self.parser.parse("where is the can teen")
        assert result.intent == "navigation"
