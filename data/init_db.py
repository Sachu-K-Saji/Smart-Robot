"""
Database initialization script.
Creates the campus.db SQLite database with schema and sample data.
Run this script directly or via the bootstrap script.
"""
import sqlite3
import sys
from pathlib import Path

# Allow running both as a script and as an import
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "campus.db"


def create_database(db_path: str = None):
    """Create the database schema and populate with sample data."""
    if db_path is None:
        db_path = str(DB_PATH)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ── Schema ────────────────────────────────────────────────
    cursor.executescript("""
        DROP TABLE IF EXISTS faculty_fts;
        DROP TABLE IF EXISTS routes;
        DROP TABLE IF EXISTS locations;
        DROP TABLE IF EXISTS students;
        DROP TABLE IF EXISTS faculty;
        DROP TABLE IF EXISTS departments;

        CREATE TABLE departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            building TEXT NOT NULL,
            floor INTEGER DEFAULT 0,
            head_faculty_id INTEGER,
            phone TEXT
        );

        CREATE TABLE faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department_id INTEGER NOT NULL,
            designation TEXT NOT NULL,
            email TEXT,
            office_location TEXT,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );

        CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_number TEXT UNIQUE NOT NULL,
            department_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            section TEXT,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );

        CREATE TABLE locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            node_id TEXT UNIQUE NOT NULL,
            building TEXT,
            location_type TEXT NOT NULL
        );

        CREATE TABLE routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node TEXT NOT NULL,
            destination_node TEXT NOT NULL,
            verbal_directions TEXT NOT NULL,
            video_path TEXT,
            estimated_time_minutes REAL
        );

        CREATE VIRTUAL TABLE faculty_fts USING fts5(
            name, designation, content='faculty', content_rowid='id'
        );
    """)

    # ── Sample Departments ────────────────────────────────────
    departments = [
        ("Computer Science and Engineering", "Block A", 2, None, "044-27152000"),
        ("Electronics and Communication Engineering", "Block B", 1, None, "044-27152001"),
        ("Mechanical Engineering", "Block C", 1, None, "044-27152002"),
        ("Civil Engineering", "Block D", 0, None, "044-27152003"),
        ("Information Technology", "Block A", 3, None, "044-27152004"),
    ]
    cursor.executemany(
        "INSERT INTO departments (name, building, floor, head_faculty_id, phone) "
        "VALUES (?, ?, ?, ?, ?)",
        departments,
    )

    # ── Sample Faculty ────────────────────────────────────────
    faculty = [
        ("Dr. Rajesh Kumar", 1, "Professor and HOD", "rajesh.k@college.edu", "Block A, Room 201"),
        ("Dr. Priya Sharma", 1, "Associate Professor", "priya.s@college.edu", "Block A, Room 205"),
        ("Dr. Suresh Babu", 2, "Professor and HOD", "suresh.b@college.edu", "Block B, Room 101"),
        ("Dr. Meena Devi", 2, "Assistant Professor", "meena.d@college.edu", "Block B, Room 105"),
        ("Dr. Arun Prakash", 3, "Professor and HOD", "arun.p@college.edu", "Block C, Room 102"),
        ("Prof. Kavitha Rajan", 4, "Associate Professor", "kavitha.r@college.edu", "Block D, Room 003"),
        ("Dr. Venkatesh Murthy", 5, "Professor and HOD", "venkatesh.m@college.edu", "Block A, Room 301"),
        ("Dr. Lakshmi Narayanan", 1, "Assistant Professor", "lakshmi.n@college.edu", "Block A, Room 210"),
    ]
    cursor.executemany(
        "INSERT INTO faculty (name, department_id, designation, email, office_location) "
        "VALUES (?, ?, ?, ?, ?)",
        faculty,
    )

    # Update department heads
    cursor.execute("UPDATE departments SET head_faculty_id = 1 WHERE id = 1")
    cursor.execute("UPDATE departments SET head_faculty_id = 3 WHERE id = 2")
    cursor.execute("UPDATE departments SET head_faculty_id = 5 WHERE id = 3")
    cursor.execute("UPDATE departments SET head_faculty_id = 6 WHERE id = 4")
    cursor.execute("UPDATE departments SET head_faculty_id = 7 WHERE id = 5")

    # ── Sample Students ───────────────────────────────────────
    students = [
        ("Aravind Shankar", "CS2024001", 1, 2, "A"),
        ("Divya Krishnan", "CS2024002", 1, 2, "A"),
        ("Mohammed Faisal", "EC2024001", 2, 2, "A"),
        ("Sneha Reddy", "ME2024001", 3, 1, "B"),
        ("Karthik Raja", "CE2024001", 4, 3, "A"),
        ("Pooja Nair", "IT2024001", 5, 2, "A"),
    ]
    cursor.executemany(
        "INSERT INTO students (name, roll_number, department_id, year, section) "
        "VALUES (?, ?, ?, ?, ?)",
        students,
    )

    # ── Sample Locations ──────────────────────────────────────
    locations = [
        ("Main Gate", "main_gate", None, "entrance"),
        ("Central Library", "library", "Library Building", "building"),
        ("CS Department", "cs_dept", "Block A", "department"),
        ("ECE Department", "ece_dept", "Block B", "department"),
        ("Mechanical Department", "mech_dept", "Block C", "department"),
        ("Civil Department", "civil_dept", "Block D", "department"),
        ("IT Department", "it_dept", "Block A", "department"),
        ("Auditorium", "auditorium", "Main Building", "building"),
        ("Cafeteria", "cafeteria", "Cafeteria Building", "facility"),
        ("Sports Ground", "sports_ground", None, "outdoor"),
        ("Admin Office", "admin_office", "Main Building", "office"),
        ("Parking Lot", "parking", None, "outdoor"),
        ("Fountain Plaza", "fountain", None, "landmark"),
        ("Workshop", "workshop", "Block C", "facility"),
        ("Computer Lab", "comp_lab", "Block A", "lab"),
    ]
    cursor.executemany(
        "INSERT INTO locations (name, node_id, building, location_type) "
        "VALUES (?, ?, ?, ?)",
        locations,
    )

    # ── Sample Routes ─────────────────────────────────────────
    routes = [
        ("main_gate", "cs_dept",
         "From the main gate, walk straight past the fountain plaza. "
         "Take the first right towards Block A. "
         "The CS department is on the second floor.",
         "videos/main_gate_to_cs_dept.mp4", 5.0),
        ("main_gate", "library",
         "From the main gate, walk straight for about 2 minutes. "
         "The library will be on your right, past the fountain.",
         "videos/main_gate_to_library.mp4", 3.0),
        ("library", "cafeteria",
         "Exit the library from the main entrance. "
         "Turn left and walk for about 1 minute. "
         "The cafeteria is the building with the green roof.",
         None, 2.0),
    ]
    cursor.executemany(
        "INSERT INTO routes (source_node, destination_node, verbal_directions, "
        "video_path, estimated_time_minutes) VALUES (?, ?, ?, ?, ?)",
        routes,
    )

    # ── Populate FTS5 Index ───────────────────────────────────
    cursor.execute(
        "INSERT INTO faculty_fts (rowid, name, designation) "
        "SELECT id, name, designation FROM faculty"
    )

    conn.commit()
    conn.close()
    print(f"Database created at: {db_path}")


if __name__ == "__main__":
    create_database()
