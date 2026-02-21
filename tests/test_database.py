"""Tests for the campus database module."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCampusDatabase:
    """Test suite for CampusDatabase."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        """Create a fresh test database for each test."""
        from data.init_db import create_database
        from modules.database import CampusDatabase

        db_file = str(tmp_path / "test_campus.db")
        create_database(db_file)
        self.db = CampusDatabase(db_file)
        yield
        self.db.close()

    def test_get_all_departments(self):
        depts = self.db.get_all_departments()
        assert len(depts) == 5
        names = [d["name"] for d in depts]
        assert "Computer Science and Engineering" in names

    def test_get_department_by_exact_name(self):
        dept = self.db.get_department_by_name("Computer Science and Engineering")
        assert dept is not None
        assert dept["building"] == "Block A"

    def test_get_department_by_fuzzy_name(self):
        dept = self.db.get_department_by_name("computer science")
        assert dept is not None
        assert "Computer Science" in dept["name"]

    def test_search_faculty_fts(self):
        results = self.db.search_faculty("Rajesh")
        assert len(results) >= 1
        assert "Rajesh" in results[0]["name"]

    def test_search_faculty_fuzzy_fallback(self):
        results = self.db.search_faculty("rajsh kumar")  # Typo
        assert len(results) >= 1

    def test_search_student_by_roll(self):
        results = self.db.search_student("CS2024001")
        assert len(results) == 1
        assert results[0]["name"] == "Aravind Shankar"

    def test_search_student_by_name(self):
        results = self.db.search_student("Divya")
        assert len(results) >= 1

    def test_search_location(self):
        loc = self.db.search_location("library")
        assert loc is not None
        assert loc["node_id"] == "library"

    def test_get_all_location_names(self):
        names = self.db.get_all_location_names()
        assert len(names) == 15
        assert "Main Gate" in names

    def test_get_route(self):
        route = self.db.get_route("main_gate", "cs_dept")
        assert route is not None
        assert route["estimated_time_minutes"] == 5.0
