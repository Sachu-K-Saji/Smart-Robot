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

    # ── College queries ─────────────────────────────────────

    def test_get_all_colleges(self):
        colleges = self.db.get_all_colleges()
        assert len(colleges) == 1
        assert colleges[0]["name"] == "Sample College of Engineering"

    def test_get_college_by_id(self):
        college = self.db.get_college_by_id(1)
        assert college is not None
        assert college["short_name"] == "SCE"

    # ── Department queries ────────────────────────────────────

    def test_get_all_departments(self):
        depts = self.db.get_all_departments()
        assert len(depts) == 5
        names = [d["name"] for d in depts]
        assert "Computer Science and Engineering" in names

    def test_get_all_departments_include_college_name(self):
        depts = self.db.get_all_departments()
        assert "college_name" in depts[0]
        assert depts[0]["college_name"] == "Sample College of Engineering"

    def test_get_department_by_exact_name(self):
        dept = self.db.get_department_by_name("Computer Science and Engineering")
        assert dept is not None
        assert dept["building"] == "Block A"
        assert "college_name" in dept

    def test_get_department_by_fuzzy_name(self):
        dept = self.db.get_department_by_name("computer science")
        assert dept is not None
        assert "Computer Science" in dept["name"]

    def test_get_departments_by_college(self):
        depts = self.db.get_departments_by_college(1)
        assert len(depts) == 5

    # ── Faculty queries ───────────────────────────────────────

    def test_search_faculty_fts(self):
        results = self.db.search_faculty("Rajesh")
        assert len(results) >= 1
        assert "Rajesh" in results[0]["name"]

    def test_search_faculty_includes_joined_fields(self):
        results = self.db.search_faculty("Rajesh")
        assert len(results) >= 1
        assert "department_name" in results[0]
        assert "college_name" in results[0]

    def test_search_faculty_fuzzy_fallback(self):
        results = self.db.search_faculty("rajsh kumar")  # Typo
        assert len(results) >= 1

    def test_get_faculty_by_department(self):
        faculty = self.db.get_faculty_by_department(1)
        assert len(faculty) >= 2  # CS dept has multiple faculty

    # ── Student queries ───────────────────────────────────────

    def test_search_student_by_roll(self):
        results = self.db.search_student("CS2024001")
        assert len(results) == 1
        assert results[0]["name"] == "Aravind Shankar"

    def test_search_student_by_name(self):
        results = self.db.search_student("Divya")
        assert len(results) >= 1

    # ── Location queries ──────────────────────────────────────

    def test_search_location(self):
        loc = self.db.search_location("library")
        assert loc is not None
        assert loc["node_id"] == "library"

    def test_get_all_location_names(self):
        names = self.db.get_all_location_names()
        assert len(names) == 15
        assert "Main Gate" in names

    def test_get_location_by_node_id(self):
        loc = self.db.get_location_by_node_id("library")
        assert loc is not None
        assert loc["name"] == "Central Library"

    # ── Route queries ─────────────────────────────────────────

    def test_get_route(self):
        route = self.db.get_route("main_gate", "cs_dept")
        assert route is not None
        assert route["estimated_time_minutes"] == 5.0

    # ── Knowledge base queries ────────────────────────────────

    def test_search_knowledge_base_fts(self):
        results = self.db.search_knowledge_base("library books")
        assert len(results) >= 1
        assert "library" in results[0]["content"].lower()

    def test_search_knowledge_base_fuzzy_fallback(self):
        results = self.db.search_knowledge_base("premier institution")
        assert len(results) >= 1

    def test_search_knowledge_base_no_results(self):
        results = self.db.search_knowledge_base("xyzzy nonexistent topic")
        assert len(results) == 0

    # ── FTS5 special character handling ─────────────────────────

    def test_fts5_special_chars_plus(self):
        """FTS5 query with '+' should not crash."""
        results = self.db.search_faculty("Dr. + Rajesh")
        assert isinstance(results, list)

    def test_fts5_special_chars_minus(self):
        """FTS5 query with '-' should not crash."""
        results = self.db.search_faculty("Rajesh - Kumar")
        assert isinstance(results, list)

    def test_fts5_special_chars_star(self):
        """FTS5 query with '*' should not crash."""
        results = self.db.search_knowledge_base("library * books")
        assert isinstance(results, list)

    def test_fts5_special_chars_quotes(self):
        """FTS5 query with double quotes should not crash."""
        results = self.db.search_faculty('"Rajesh"')
        assert isinstance(results, list)

    # ── New JOIN-based methods ─────────────────────────────────

    def test_search_student_with_department(self):
        """search_student_with_department should include department_name."""
        results = self.db.search_student_with_department("CS2024001")
        assert len(results) == 1
        assert results[0]["name"] == "Aravind Shankar"
        assert "department_name" in results[0]
        assert "Computer Science" in results[0]["department_name"]

    def test_search_student_with_department_by_name(self):
        results = self.db.search_student_with_department("Divya")
        assert len(results) >= 1
        assert "department_name" in results[0]

    def test_get_department_with_head(self):
        """get_department_with_head should include head_name."""
        dept = self.db.get_department_with_head("Computer Science and Engineering")
        assert dept is not None
        assert "head_name" in dept
        assert dept["head_name"] is not None
