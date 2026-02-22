"""
Import crawled college data into the campus robot database.
Reads faculty_summary.json and lourdes_matha_all_data.json,
then populates colleges, departments, faculty, and knowledge_base tables.

Usage:
    python data/import_crawled_data.py
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "campus.db"
FACULTY_FILE = BASE_DIR / "data" / "faculty_summary.json"
CRAWLED_FILE = BASE_DIR / "data" / "lourdes_matha_all_data.json"

# Content to skip when importing paragraphs/headings into knowledge base
NOISE_PHRASES = {
    "copyright", "web division", "all rights reserved",
    "quick links", "follow us", "important links",
}


def is_noise(text):
    """Check if text is boilerplate/noise content."""
    lower = text.strip().lower()
    if len(lower) < 5:
        return True
    return any(phrase in lower for phrase in NOISE_PHRASES)


def import_data(db_path: str = None):
    """Import crawled data into the database."""
    if db_path is None:
        db_path = str(DB_PATH)

    if not FACULTY_FILE.exists():
        print(f"Error: {FACULTY_FILE} not found. Run the crawler first.")
        sys.exit(1)
    if not CRAWLED_FILE.exists():
        print(f"Error: {CRAWLED_FILE} not found. Run the crawler first.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # ── Clear existing data (keep locations and routes for navigation) ──
    # Students reference departments via FK, so clear them too
    cursor.executescript("""
        DELETE FROM faculty_fts;
        DELETE FROM knowledge_base_fts;
        DELETE FROM knowledge_base;
        DELETE FROM students;
        DELETE FROM faculty;
        DELETE FROM departments;
        DELETE FROM colleges;
    """)

    # ══════════════════════════════════════════════════════════
    # Part 1: Import structured faculty data
    # ══════════════════════════════════════════════════════════
    with open(FACULTY_FILE, "r", encoding="utf-8") as f:
        faculty_data = json.load(f)

    print(f"\nImporting from: {FACULTY_FILE.name}")
    print(f"Institution: {faculty_data['institution']}")

    total_faculty = 0
    total_depts = 0

    for college_data in faculty_data["colleges"]:
        # Insert college
        cursor.execute(
            "INSERT INTO colleges (name, short_name, website) VALUES (?, ?, ?)",
            (
                college_data["name"],
                college_data["name"].split("—")[0].strip() if "—" in college_data["name"] else college_data["name"][:10],
                college_data.get("website", ""),
            ),
        )
        college_id = cursor.lastrowid
        print(f"\n  College: {college_data['name']}")

        for dept_data in college_data.get("departments", []):
            # Insert department
            cursor.execute(
                "INSERT INTO departments (name, college_id, building, floor, phone) "
                "VALUES (?, ?, ?, ?, ?)",
                (dept_data["department"], college_id, None, None, None),
            )
            dept_id = cursor.lastrowid
            total_depts += 1

            dept_faculty_count = 0
            head_faculty_id = None

            # Insert teaching faculty
            for fac in dept_data.get("teaching_faculty", []):
                cursor.execute(
                    "INSERT INTO faculty (name, department_id, designation, "
                    "qualification, email, phone, office_location) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        fac["name"],
                        dept_id,
                        fac.get("designation", ""),
                        fac.get("qualification", ""),
                        fac.get("email", ""),
                        fac.get("phone", ""),
                        None,
                    ),
                )
                fac_id = cursor.lastrowid
                dept_faculty_count += 1
                total_faculty += 1

                # First HOD/HoD/Principal becomes dept head
                desig_lower = fac.get("designation", "").lower()
                if head_faculty_id is None and ("hod" in desig_lower or "principal" in desig_lower):
                    head_faculty_id = fac_id

            # Insert technical staff
            for staff in dept_data.get("technical_staff", []):
                cursor.execute(
                    "INSERT INTO faculty (name, department_id, designation, "
                    "qualification, email, phone, office_location) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        staff["name"],
                        dept_id,
                        staff.get("designation", "Technical Staff"),
                        staff.get("qualification", ""),
                        staff.get("email", ""),
                        staff.get("phone", ""),
                        None,
                    ),
                )
                total_faculty += 1

            # Update department head
            if head_faculty_id:
                cursor.execute(
                    "UPDATE departments SET head_faculty_id = ? WHERE id = ?",
                    (head_faculty_id, dept_id),
                )

            print(f"    {dept_data['department']}: {dept_faculty_count} faculty")

    # ══════════════════════════════════════════════════════════
    # Part 2: Import all crawled content into knowledge base
    # ══════════════════════════════════════════════════════════
    with open(CRAWLED_FILE, "r", encoding="utf-8") as f:
        all_pages = json.load(f)

    print(f"\nImporting knowledge base from: {CRAWLED_FILE.name}")
    print(f"Total pages: {len(all_pages)}")

    kb_count = 0

    for page in all_pages:
        source = page.get("source", "Unknown")
        url = page.get("url", "")
        title = page.get("page_title", "No title")

        # Import headings as knowledge base entries
        for heading in page.get("headings", []):
            heading = heading.strip()
            if heading and not is_noise(heading):
                cursor.execute(
                    "INSERT INTO knowledge_base (source, url, page_title, content, content_type) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source, url, title, heading, "heading"),
                )
                kb_count += 1

        # Import sub_headings
        for sub in page.get("sub_headings", []):
            sub = sub.strip()
            if sub and not is_noise(sub):
                cursor.execute(
                    "INSERT INTO knowledge_base (source, url, page_title, content, content_type) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source, url, title, sub, "sub_heading"),
                )
                kb_count += 1

        # Import paragraphs (the main content)
        for para in page.get("paragraphs", []):
            para = para.strip()
            if para and not is_noise(para) and len(para) > 10:
                cursor.execute(
                    "INSERT INTO knowledge_base (source, url, page_title, content, content_type) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source, url, title, para, "paragraph"),
                )
                kb_count += 1

    # ══════════════════════════════════════════════════════════
    # Part 3: Rebuild FTS5 indexes
    # ══════════════════════════════════════════════════════════
    cursor.execute(
        "INSERT INTO faculty_fts (rowid, name, designation) "
        "SELECT id, name, designation FROM faculty"
    )
    cursor.execute(
        "INSERT INTO knowledge_base_fts (rowid, page_title, content) "
        "SELECT id, page_title, content FROM knowledge_base"
    )

    conn.commit()

    # ── Summary ───────────────────────────────────────────────
    college_count = cursor.execute("SELECT COUNT(*) FROM colleges").fetchone()[0]
    dept_count = cursor.execute("SELECT COUNT(*) FROM departments").fetchone()[0]
    fac_count = cursor.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
    kb_total = cursor.execute("SELECT COUNT(*) FROM knowledge_base").fetchone()[0]

    print(f"\n{'=' * 50}")
    print(f"Import complete!")
    print(f"  Colleges:        {college_count}")
    print(f"  Departments:     {dept_count}")
    print(f"  Faculty/Staff:   {fac_count}")
    print(f"  Knowledge base:  {kb_total} entries")
    print(f"  Database:        {db_path}")
    print(f"{'=' * 50}")

    conn.close()


if __name__ == "__main__":
    import_data()
