"""Tests for thread safety across modules."""
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDatabaseThreadSafety:
    """Test concurrent database access."""

    @pytest.fixture(autouse=True)
    def setup_db(self, test_db):
        self.db = test_db

    def test_concurrent_reads_no_crash(self):
        """4 threads reading concurrently should not crash or corrupt data."""
        errors = []

        def read_task(task_id):
            try:
                for _ in range(20):
                    if task_id % 4 == 0:
                        self.db.get_all_departments()
                    elif task_id % 4 == 1:
                        self.db.search_faculty("Rajesh")
                    elif task_id % 4 == 2:
                        self.db.search_student("CS2024001")
                    else:
                        self.db.search_location("library")
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(read_task, i) for i in range(4)]
            for f in as_completed(futures):
                f.result()  # Re-raise any exception

        assert len(errors) == 0, f"Concurrent read errors: {errors}"

    def test_concurrent_reads_return_correct_data(self):
        """Concurrent reads should return consistent data."""
        results = {"depts": [], "faculty": []}

        def read_depts():
            for _ in range(10):
                depts = self.db.get_all_departments()
                results["depts"].append(len(depts))

        def read_faculty():
            for _ in range(10):
                faculty = self.db.search_faculty("Rajesh")
                results["faculty"].append(len(faculty))

        threads = [
            threading.Thread(target=read_depts),
            threading.Thread(target=read_faculty),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should return the same count
        assert len(set(results["depts"])) == 1, "Department counts varied across reads"
        assert all(c >= 1 for c in results["faculty"]), "Faculty search returned 0 results"

    def test_fts5_thread_safety(self):
        """FTS5 searches should be thread-safe."""
        errors = []

        def search_kb(query):
            try:
                for _ in range(10):
                    self.db.search_knowledge_base(query)
                    self.db.search_faculty(query)
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(search_kb, q)
                for q in ["library", "premier", "Rajesh"]
            ]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0


class TestStateAccessThreadSafety:
    """Test that state machine access is thread-safe."""

    def test_concurrent_safe_transitions(self):
        """Multiple threads calling _safe_transition should not crash."""
        from unittest.mock import patch, MagicMock

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
            robot = CampusRobot()

            errors = []

            def try_transitions():
                try:
                    for _ in range(50):
                        # These will mostly fail (invalid transitions) but should not crash
                        robot._safe_transition("wake_up")
                        robot._safe_transition("error")
                except Exception as e:
                    errors.append(str(e))

            threads = [threading.Thread(target=try_transitions) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"Thread safety errors: {errors}"
