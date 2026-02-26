"""
SQLite3 database interface for campus information queries.
Supports FTS5 full-text search and fuzzy matching fallback.
Thread-safe with WAL journal mode for concurrent read performance.
"""
import sqlite3
import threading
from typing import Optional

from fuzzywuzzy import fuzz


class CampusDatabase:
    """Interface to the campus SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._faculty_cache = None

    def close(self):
        """Close the database connection."""
        self.conn.close()

    # ── Thread-Safe Helpers ──────────────────────────────────

    def _fetchall(self, query, params=()):
        """Execute a query and return all rows as dicts, under lock."""
        with self._lock:
            cursor = self.conn.execute(query, params)
            return [dict(row) for row in cursor]

    def _fetchone(self, query, params=()):
        """Execute a query and return one row as dict (or None), under lock."""
        with self._lock:
            cursor = self.conn.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def _execute(self, query, params=()):
        """Execute a write query under lock, then commit."""
        with self._lock:
            self.conn.execute(query, params)
            self.conn.commit()

    # ── FTS5 Query Escaping ──────────────────────────────────

    @staticmethod
    def _escape_fts5_query(query: str) -> str:
        """Wrap each word in double quotes to neutralize FTS5 operators (+, -, *, etc.)."""
        words = query.strip().split()
        return " ".join(f'"{w}"' for w in words if w)

    # ── Lazy Faculty Cache ───────────────────────────────────

    def _get_faculty_cache(self) -> list[dict]:
        """Load all faculty (with JOINs) once, then return cached list."""
        if self._faculty_cache is None:
            self._faculty_cache = self._fetchall(
                "SELECT f.*, d.name AS department_name, "
                "c.name AS college_name, c.short_name AS college_short_name "
                "FROM faculty f "
                "LEFT JOIN departments d ON f.department_id = d.id "
                "LEFT JOIN colleges c ON d.college_id = c.id"
            )
        return self._faculty_cache

    # ── College Queries ─────────────────────────────────────

    def get_all_colleges(self) -> list[dict]:
        """Return all colleges."""
        return self._fetchall("SELECT * FROM colleges")

    def get_college_by_id(self, college_id: int) -> Optional[dict]:
        """Look up a college by ID."""
        return self._fetchone(
            "SELECT * FROM colleges WHERE id = ?", (college_id,)
        )

    # ── Department Queries ────────────────────────────────────

    def get_department_by_name(self, name: str) -> Optional[dict]:
        """Look up department by exact or fuzzy name match.
        Returns department dict with college_name included."""
        row = self._fetchone(
            "SELECT d.*, c.name AS college_name, c.short_name AS college_short_name "
            "FROM departments d LEFT JOIN colleges c ON d.college_id = c.id "
            "WHERE LOWER(d.name) = LOWER(?)", (name,)
        )
        if row:
            return row

        # Fuzzy match
        all_depts = self._fetchall(
            "SELECT d.*, c.name AS college_name, c.short_name AS college_short_name "
            "FROM departments d LEFT JOIN colleges c ON d.college_id = c.id"
        )
        best_match = None
        best_score = 0
        for dept in all_depts:
            score = fuzz.partial_ratio(name.lower(), dept["name"].lower())
            if score > best_score:
                best_score = score
                best_match = dept
        if best_score >= 70:
            return best_match
        return None

    def get_all_departments(self) -> list[dict]:
        """Return all departments with college info."""
        return self._fetchall(
            "SELECT d.*, c.name AS college_name, c.short_name AS college_short_name "
            "FROM departments d LEFT JOIN colleges c ON d.college_id = c.id "
            "LIMIT 100"
        )

    def get_departments_by_college(self, college_id: int) -> list[dict]:
        """Get all departments in a specific college."""
        return self._fetchall(
            "SELECT * FROM departments WHERE college_id = ?", (college_id,)
        )

    def get_department_with_head(self, dept_name: str) -> Optional[dict]:
        """Look up a department by name with its HOD name in one query (LEFT JOIN)."""
        return self._fetchone(
            "SELECT d.*, c.name AS college_name, c.short_name AS college_short_name, "
            "f.name AS head_name, f.designation AS head_designation, "
            "f.email AS head_email, f.phone AS head_phone "
            "FROM departments d "
            "LEFT JOIN colleges c ON d.college_id = c.id "
            "LEFT JOIN faculty f ON d.head_faculty_id = f.id "
            "WHERE LOWER(d.name) = LOWER(?)", (dept_name,)
        )

    # ── Faculty Queries ───────────────────────────────────────

    def search_faculty(self, query: str) -> list[dict]:
        """Search faculty using FTS5 full-text search.
        Returns faculty with department and college info joined."""
        escaped = self._escape_fts5_query(query)
        if not escaped:
            return self._fuzzy_search_faculty(query)

        try:
            results = self._fetchall(
                "SELECT f.*, d.name AS department_name, "
                "c.name AS college_name, c.short_name AS college_short_name "
                "FROM faculty f "
                "JOIN faculty_fts fts ON f.id = fts.rowid "
                "LEFT JOIN departments d ON f.department_id = d.id "
                "LEFT JOIN colleges c ON d.college_id = c.id "
                "WHERE faculty_fts MATCH ? ORDER BY rank",
                (escaped,),
            )
            if results:
                return results
        except sqlite3.OperationalError:
            pass  # FTS syntax error, fall through to fuzzy

        return self._fuzzy_search_faculty(query)

    def _fuzzy_search_faculty(self, query: str, threshold: int = 70) -> list[dict]:
        """Fuzzy match against all faculty names using cached data."""
        faculty_list = self._get_faculty_cache()
        matches = []
        for fac in faculty_list:
            score = fuzz.partial_ratio(query.lower(), fac["name"].lower())
            if score >= threshold:
                matches.append((score, fac))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    def get_faculty_by_department(self, department_id: int) -> list[dict]:
        """Get all faculty in a department."""
        return self._fetchall(
            "SELECT * FROM faculty WHERE department_id = ?", (department_id,)
        )

    def search_faculty_by_role(self, role: str, college_query: str = None) -> list[dict]:
        """Search faculty by designation/role (e.g., 'Principal', 'HOD').
        Optionally filter by college name."""
        query = """
            SELECT f.*, d.name AS department_name,
                   c.name AS college_name, c.short_name AS college_short_name
            FROM faculty f
            JOIN departments d ON f.department_id = d.id
            LEFT JOIN colleges c ON d.college_id = c.id
            WHERE LOWER(f.designation) LIKE LOWER(?)
        """
        params = [f"%{role}%"]

        if college_query:
            query += " AND (LOWER(c.name) LIKE LOWER(?) OR LOWER(c.short_name) LIKE LOWER(?))"
            params.extend([f"%{college_query}%", f"%{college_query}%"])

        return self._fetchall(query, params)

    # ── Student Queries ───────────────────────────────────────

    def search_student(self, query: str) -> list[dict]:
        """Search student by name or roll number (fuzzy)."""
        row = self._fetchone(
            "SELECT * FROM students WHERE UPPER(roll_number) = UPPER(?)", (query,)
        )
        if row:
            return [row]

        all_students = self._fetchall("SELECT * FROM students")
        matches = []
        for student in all_students:
            score = fuzz.partial_ratio(query.lower(), student["name"].lower())
            if score >= 70:
                matches.append((score, student))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    def search_student_with_department(self, query: str) -> list[dict]:
        """Search student by name or roll number with department info (LEFT JOIN).
        Avoids N+1 queries by fetching department name in one shot."""
        row = self._fetchone(
            "SELECT s.*, d.name AS department_name, "
            "c.name AS college_name, c.short_name AS college_short_name "
            "FROM students s "
            "LEFT JOIN departments d ON s.department_id = d.id "
            "LEFT JOIN colleges c ON d.college_id = c.id "
            "WHERE UPPER(s.roll_number) = UPPER(?)", (query,)
        )
        if row:
            return [row]

        all_students = self._fetchall(
            "SELECT s.*, d.name AS department_name, "
            "c.name AS college_name, c.short_name AS college_short_name "
            "FROM students s "
            "LEFT JOIN departments d ON s.department_id = d.id "
            "LEFT JOIN colleges c ON d.college_id = c.id"
        )
        matches = []
        for student in all_students:
            score = fuzz.partial_ratio(query.lower(), student["name"].lower())
            if score >= 70:
                matches.append((score, student))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    # ── Location Queries ──────────────────────────────────────

    def get_location_by_node_id(self, node_id: str) -> Optional[dict]:
        """Look up a location by its graph node ID."""
        return self._fetchone(
            "SELECT * FROM locations WHERE node_id = ?", (node_id,)
        )

    def search_location(self, query: str) -> Optional[dict]:
        """Fuzzy search for a location by name."""
        all_locations = self._fetchall("SELECT * FROM locations")
        best_match = None
        best_score = 0
        for loc in all_locations:
            score = fuzz.partial_ratio(query.lower(), loc["name"].lower())
            if score > best_score:
                best_score = score
                best_match = loc
        if best_score >= 70:
            return best_match
        return None

    def get_all_location_names(self) -> list[str]:
        """Return all location names (for intent parser entity matching)."""
        rows = self._fetchall("SELECT name FROM locations")
        return [row["name"] for row in rows]

    def get_all_faculty_names(self) -> list[str]:
        """Return all faculty names (for intent parser entity matching)."""
        rows = self._fetchall("SELECT name FROM faculty")
        return [row["name"] for row in rows]

    def get_all_department_names(self) -> list[str]:
        """Return all department names (for intent parser entity matching)."""
        rows = self._fetchall("SELECT name FROM departments")
        return [row["name"] for row in rows]

    # ── Route Queries ─────────────────────────────────────────

    def get_route(self, source_node: str, dest_node: str) -> Optional[dict]:
        """Look up a pre-recorded route between two nodes."""
        return self._fetchone(
            "SELECT * FROM routes WHERE source_node = ? AND destination_node = ?",
            (source_node, dest_node),
        )

    # ── Knowledge Base Queries ────────────────────────────────

    def search_knowledge_base(self, query: str, limit: int = 3) -> list[dict]:
        """Search the knowledge base using FTS5.
        Returns the top matching paragraphs with page context."""
        escaped = self._escape_fts5_query(query)
        if not escaped:
            return self._fuzzy_search_knowledge_base(query, limit)

        try:
            results = self._fetchall(
                "SELECT kb.*, rank FROM knowledge_base kb "
                "JOIN knowledge_base_fts fts ON kb.id = fts.rowid "
                "WHERE knowledge_base_fts MATCH ? "
                "AND kb.content_type = 'paragraph' "
                "ORDER BY rank LIMIT ?",
                (escaped, limit),
            )
            if results:
                return results
        except sqlite3.OperationalError:
            pass

        # Fuzzy fallback for short or unusual queries
        return self._fuzzy_search_knowledge_base(query, limit)

    def _fuzzy_search_knowledge_base(self, query: str, limit: int = 3) -> list[dict]:
        """Fuzzy search knowledge base paragraphs."""
        all_kb = self._fetchall(
            "SELECT * FROM knowledge_base WHERE content_type = 'paragraph'"
        )
        matches = []
        query_lower = query.lower()
        for entry in all_kb:
            score = fuzz.partial_ratio(query_lower, entry["content"].lower())
            if score >= 60:
                matches.append((score, entry))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches[:limit]]
