"""
Campus navigation using NetworkX graph with Dijkstra shortest path.
Loads the campus map JSON and provides direction generation.
"""
import json
from typing import Optional

import networkx as nx


class CampusNavigator:
    """Graph-based campus navigation engine."""

    def __init__(self, map_path: str):
        self.graph = nx.Graph()
        self.node_data = {}
        self.edge_directions = {}
        self._load_map(map_path)

    def _load_map(self, map_path: str):
        """Load campus map JSON into a NetworkX graph."""
        with open(map_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for node_id, attrs in data["nodes"].items():
            self.graph.add_node(node_id, **attrs)
            self.node_data[node_id] = attrs

        for edge in data["edges"]:
            src, dst = edge["from"], edge["to"]
            distance = edge["distance"]
            direction = edge["direction"]

            self.graph.add_edge(src, dst, weight=distance)

            self.edge_directions[(src, dst)] = direction
            if (dst, src) not in self.edge_directions:
                self.edge_directions[(dst, src)] = (
                    f"Walk from {self.node_data.get(dst, {}).get('name', dst)} "
                    f"towards {self.node_data.get(src, {}).get('name', src)}."
                )

    def find_shortest_path(self, source: str, destination: str) -> Optional[dict]:
        """
        Find shortest path using Dijkstra's algorithm.

        Returns dict with:
            - path: list of node IDs
            - total_distance: sum of edge weights
            - directions: list of verbal direction strings
            - steps: list of (from_node, to_node, direction) tuples
        """
        if source not in self.graph or destination not in self.graph:
            return None

        try:
            path = nx.dijkstra_path(self.graph, source, destination, weight="weight")
            total_distance = nx.dijkstra_path_length(
                self.graph, source, destination, weight="weight"
            )
        except nx.NetworkXNoPath:
            return None

        steps = []
        directions = []
        for i in range(len(path) - 1):
            src, dst = path[i], path[i + 1]
            direction = self.edge_directions.get(
                (src, dst),
                f"Continue to {self.node_data.get(dst, {}).get('name', dst)}.",
            )
            steps.append((src, dst, direction))
            directions.append(direction)

        return {
            "path": path,
            "total_distance": total_distance,
            "directions": directions,
            "steps": steps,
        }

    def get_directions_text(
        self, source: str, destination: str, max_steps_per_segment: int = 3
    ) -> Optional[str]:
        """
        Get formatted verbal directions as a single text string.
        Breaks long routes into segments of max_steps_per_segment steps.
        """
        result = self.find_shortest_path(source, destination)
        if result is None:
            return None

        src_name = self.node_data.get(source, {}).get("name", source)
        dst_name = self.node_data.get(destination, {}).get("name", destination)

        parts = [f"Here are the directions from {src_name} to {dst_name}:"]

        for i, direction in enumerate(result["directions"], 1):
            parts.append(f"Step {i}: {direction}")

            if i % max_steps_per_segment == 0 and i < len(result["directions"]):
                parts.append("Let me know when you are ready for the next steps.")

        estimated_minutes = round(result["total_distance"] / 80, 1)
        parts.append(
            f"The total walking distance is approximately {estimated_minutes} minutes."
        )

        return " ".join(parts)

    def get_node_name(self, node_id: str) -> str:
        """Get the human-readable name of a node."""
        return self.node_data.get(node_id, {}).get("name", node_id)

    def get_all_node_ids(self) -> list[str]:
        """Return all node IDs in the graph."""
        return list(self.graph.nodes)

    def find_nearest_node_by_name(self, name: str) -> Optional[str]:
        """Find a node ID by fuzzy-matching the name."""
        name_lower = name.lower()
        for node_id, data in self.node_data.items():
            if name_lower in data.get("name", "").lower():
                return node_id
        return None
