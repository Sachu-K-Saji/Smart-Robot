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
            faculty_names=["Dr. Rajesh Kumar", "Dr. Priya Sharma"],
            department_names=["Computer Science and Engineering", "Mechanical Engineering"],
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
