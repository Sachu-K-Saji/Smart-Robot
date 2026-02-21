"""Tests for the campus navigator module."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.navigator import CampusNavigator


class TestCampusNavigator:

    @pytest.fixture(autouse=True)
    def setup_navigator(self, tmp_path):
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

        self.nav = CampusNavigator(map_path)

    def test_shortest_path_direct(self):
        result = self.nav.find_shortest_path("A", "B")
        assert result is not None
        assert result["path"] == ["A", "B"]
        assert result["total_distance"] == 100

    def test_shortest_path_via_intermediate(self):
        result = self.nav.find_shortest_path("A", "C")
        assert result is not None
        assert result["path"] == ["A", "B", "C"]
        assert result["total_distance"] == 200

    def test_shortest_path_dijkstra(self):
        # A->D direct is 200, A->B->D is 100+150=250
        result = self.nav.find_shortest_path("A", "D")
        assert result is not None
        assert result["total_distance"] == 200
        assert result["path"] == ["A", "D"]

    def test_nonexistent_node(self):
        result = self.nav.find_shortest_path("A", "Z")
        assert result is None

    def test_directions_text(self):
        text = self.nav.get_directions_text("A", "C")
        assert text is not None
        assert "Step 1" in text
        assert "Step 2" in text

    def test_get_node_name(self):
        assert self.nav.get_node_name("A") == "Point A"
        assert self.nav.get_node_name("nonexistent") == "nonexistent"
