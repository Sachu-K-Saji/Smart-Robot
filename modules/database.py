"""
SQLite3 database interface for campus information queries.
Supports FTS5 full-text search and fuzzy matching fallback.
"""
import sqlite3
from typing import Optional

from fuzzywuzzy import fuzz


class CampusDatabase:
    """Interface to the campus SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        """Close the database connection."""
        self.conn.close()

    # ── Department Queries ────────────────────────────────────

    def get_department_by_name(self, name: str) -> Optional[dict]:
        """Look up department by exact or fuzzy name match."""
        cursor = self.conn.execute(
            "SELECT * FROM departments WHERE LOWER(name) = LOWER(?)", (name,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor = self.conn.execute("SELECT * FROM departments")
        best_match = None
        best_score = 0
        for row in cursor:
            score = fuzz.partial_ratio(name.lower(), row["name"].lower())
            if score > best_score:
                best_score = score
                best_match = dict(row)
        if best_score >= 70:
            return best_match
        return None

    def get_all_departments(self) -> list[dict]:
        """Return all departments."""
        cursor = self.conn.execute("SELECT * FROM departments")
        return [dict(row) for row in cursor]

    # ── Faculty Queries ───────────────────────────────────────

    def search_faculty(self, query: str) -> list[dict]:
        """Search faculty using FTS5 full-text search."""
        try:
            cursor = self.conn.execute(
                "SELECT f.* FROM faculty f "
                "JOIN faculty_fts fts ON f.id = fts.rowid "
                "WHERE faculty_fts MATCH ? ORDER BY rank",
                (query,),
            )
            results = [dict(row) for row in cursor]
            if results:
                return results
        except sqlite3.OperationalError:
            pass  # FTS syntax error, fall through to fuzzy

        return self._fuzzy_search_faculty(query)

    def _fuzzy_search_faculty(self, query: str, threshold: int = 70) -> list[dict]:
        """Fuzzy match against all faculty names."""
        cursor = self.conn.execute("SELECT * FROM faculty")
        matches = []
        for row in cursor:
            score = fuzz.partial_ratio(query.lower(), row["name"].lower())
            if score >= threshold:
                matches.append((score, dict(row)))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    def get_faculty_by_department(self, department_id: int) -> list[dict]:
        """Get all faculty in a department."""
        cursor = self.conn.execute(
            "SELECT * FROM faculty WHERE department_id = ?", (department_id,)
        )
        return [dict(row) for row in cursor]

    # ── Student Queries ───────────────────────────────────────

    def search_student(self, query: str) -> list[dict]:
        """Search student by name or roll number (fuzzy)."""
        cursor = self.conn.execute(
            "SELECT * FROM students WHERE UPPER(roll_number) = UPPER(?)", (query,)
        )
        row = cursor.fetchone()
        if row:
            return [dict(row)]

        cursor = self.conn.execute("SELECT * FROM students")
        matches = []
        for row in cursor:
            score = fuzz.partial_ratio(query.lower(), row["name"].lower())
            if score >= 70:
                matches.append((score, dict(row)))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    # ── Location Queries ──────────────────────────────────────

    def get_location_by_node_id(self, node_id: str) -> Optional[dict]:
        """Look up a location by its graph node ID."""
        cursor = self.conn.execute(
            "SELECT * FROM locations WHERE node_id = ?", (node_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def search_location(self, query: str) -> Optional[dict]:
        """Fuzzy search for a location by name."""
        cursor = self.conn.execute("SELECT * FROM locations")
        best_match = None
        best_score = 0
        for row in cursor:
            score = fuzz.partial_ratio(query.lower(), row["name"].lower())
            if score > best_score:
                best_score = score
                best_match = dict(row)
        if best_score >= 70:
            return best_match
        return None

    def get_all_location_names(self) -> list[str]:
        """Return all location names (for intent parser entity matching)."""
        cursor = self.conn.execute("SELECT name FROM locations")
        return [row["name"] for row in cursor]

    def get_all_faculty_names(self) -> list[str]:
        """Return all faculty names (for intent parser entity matching)."""
        cursor = self.conn.execute("SELECT name FROM faculty")
        return [row["name"] for row in cursor]

    def get_all_department_names(self) -> list[str]:
        """Return all department names (for intent parser entity matching)."""
        cursor = self.conn.execute("SELECT name FROM departments")
        return [row["name"] for row in cursor]

    # ── Route Queries ─────────────────────────────────────────

    def get_route(self, source_node: str, dest_node: str) -> Optional[dict]:
        """Look up a pre-recorded route between two nodes."""
        cursor = self.conn.execute(
            "SELECT * FROM routes WHERE source_node = ? AND destination_node = ?",
            (source_node, dest_node),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
