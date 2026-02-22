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
        DROP TABLE IF EXISTS knowledge_base_fts;
        DROP TABLE IF EXISTS knowledge_base;
        DROP TABLE IF EXISTS faculty_fts;
        DROP TABLE IF EXISTS routes;
        DROP TABLE IF EXISTS locations;
        DROP TABLE IF EXISTS students;
        DROP TABLE IF EXISTS faculty;
        DROP TABLE IF EXISTS departments;
        DROP TABLE IF EXISTS colleges;

        CREATE TABLE colleges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            short_name TEXT,
            website TEXT
        );

        CREATE TABLE departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            college_id INTEGER,
            building TEXT,
            floor INTEGER DEFAULT 0,
            head_faculty_id INTEGER,
            phone TEXT,
            FOREIGN KEY (college_id) REFERENCES colleges(id)
        );

        CREATE TABLE faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department_id INTEGER NOT NULL,
            designation TEXT NOT NULL,
            qualification TEXT,
            email TEXT,
            phone TEXT,
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

        CREATE TABLE knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            url TEXT,
            page_title TEXT,
            content TEXT NOT NULL,
            content_type TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE faculty_fts USING fts5(
            name, designation, content='faculty', content_rowid='id'
        );

        CREATE VIRTUAL TABLE knowledge_base_fts USING fts5(
            page_title, content, content='knowledge_base', content_rowid='id'
        );
    """)

    # ── Sample College ───────────────────────────────────────
    cursor.execute(
        "INSERT INTO colleges (name, short_name, website) VALUES (?, ?, ?)",
        ("Sample College of Engineering", "SCE", "https://example.com"),
    )

    # ── Sample Departments ────────────────────────────────────
    departments = [
        ("Computer Science and Engineering", 1, "Block A", 2, None, "044-27152000"),
        ("Electronics and Communication Engineering", 1, "Block B", 1, None, "044-27152001"),
        ("Mechanical Engineering", 1, "Block C", 1, None, "044-27152002"),
        ("Civil Engineering", 1, "Block D", 0, None, "044-27152003"),
        ("Information Technology", 1, "Block A", 3, None, "044-27152004"),
    ]
    cursor.executemany(
        "INSERT INTO departments (name, college_id, building, floor, head_faculty_id, phone) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        departments,
    )

    # ── Sample Faculty ────────────────────────────────────────
    faculty = [
        ("Dr. Rajesh Kumar", 1, "Professor and HOD", "Ph.D in Computer Science",
         "rajesh.k@college.edu", None, "Block A, Room 201"),
        ("Dr. Priya Sharma", 1, "Associate Professor", "M.Tech, Ph.D",
         "priya.s@college.edu", None, "Block A, Room 205"),
        ("Dr. Suresh Babu", 2, "Professor and HOD", "Ph.D in VLSI Design",
         "suresh.b@college.edu", None, "Block B, Room 101"),
        ("Dr. Meena Devi", 2, "Assistant Professor", "M.Tech",
         "meena.d@college.edu", None, "Block B, Room 105"),
        ("Dr. Arun Prakash", 3, "Professor and HOD", "Ph.D in Thermal Engineering",
         "arun.p@college.edu", None, "Block C, Room 102"),
        ("Prof. Kavitha Rajan", 4, "Associate Professor", "M.E in Structural Engineering",
         "kavitha.r@college.edu", None, "Block D, Room 003"),
        ("Dr. Venkatesh Murthy", 5, "Professor and HOD", "Ph.D in Software Engineering",
         "venkatesh.m@college.edu", None, "Block A, Room 301"),
        ("Dr. Lakshmi Narayanan", 1, "Assistant Professor", "M.Tech in AI",
         "lakshmi.n@college.edu", None, "Block A, Room 210"),
    ]
    cursor.executemany(
        "INSERT INTO faculty (name, department_id, designation, qualification, "
        "email, phone, office_location) VALUES (?, ?, ?, ?, ?, ?, ?)",
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

    # ── Sample Knowledge Base ─────────────────────────────────
    kb_entries = [
        ("Sample College", "https://example.com", "Home",
         "Welcome to Sample College of Engineering, a premier institution.", "paragraph"),
        ("Sample College", "https://example.com/library", "Library",
         "The central library has over 15,000 books and journals.", "paragraph"),
    ]
    cursor.executemany(
        "INSERT INTO knowledge_base (source, url, page_title, content, content_type) "
        "VALUES (?, ?, ?, ?, ?)",
        kb_entries,
    )

    # ── Populate FTS5 Indexes ─────────────────────────────────
    cursor.execute(
        "INSERT INTO faculty_fts (rowid, name, designation) "
        "SELECT id, name, designation FROM faculty"
    )
    cursor.execute(
        "INSERT INTO knowledge_base_fts (rowid, page_title, content) "
        "SELECT id, page_title, content FROM knowledge_base"
    )

    conn.commit()
    conn.close()
    print(f"Database created at: {db_path}")


if __name__ == "__main__":
    create_database()
