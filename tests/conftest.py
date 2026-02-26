"""Shared test fixtures for the campus robot test suite."""
import json
import threading

import pytest


@pytest.fixture
def test_db(tmp_path):
    """Fresh in-memory SQLite database with sample data."""
    from data.init_db import create_database
    from modules.database import CampusDatabase

    db_file = str(tmp_path / "test_campus.db")
    create_database(db_file)
    db = CampusDatabase(db_file)
    yield db
    db.close()


@pytest.fixture
def test_navigator(tmp_path):
    """Simple 4-node test graph."""
    from modules.navigator import CampusNavigator

    test_map = {
        "nodes": {
            "A": {"name": "Point A", "x": 0, "y": 0, "type": "entrance"},
            "B": {"name": "Point B", "x": 100, "y": 0, "type": "building"},
            "C": {"name": "Point C", "x": 200, "y": 0, "type": "building"},
            "D": {"name": "Point D", "x": 100, "y": 100, "type": "building"},
        },
        "edges": [
            {"from": "A", "to": "B", "distance": 100, "direction": "Walk from A to B."},
            {"from": "B", "to": "C", "distance": 100, "direction": "Walk from B to C."},
            {"from": "B", "to": "D", "distance": 150, "direction": "Walk from B to D."},
            {"from": "A", "to": "D", "distance": 200, "direction": "Walk from A to D directly."},
        ],
    }
    map_path = str(tmp_path / "test_map.json")
    with open(map_path, "w") as f:
        json.dump(test_map, f)

    return CampusNavigator(map_path)


@pytest.fixture
def test_parser():
    """IntentParser with sample entity lists."""
    from modules.intent_parser import IntentParser

    return IntentParser(
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


@pytest.fixture
def mock_speaking_event():
    """A threading.Event for mocking the is_speaking flag."""
    return threading.Event()
