"""
Campus navigation using NetworkX graph with Dijkstra shortest path.
Loads the campus map JSON and provides direction generation.

Phase 7 hardening: graph validation, fuzzy indexed name lookup,
and rich error context on path-finding failures.
"""
import json
import logging
from typing import Optional

import networkx as nx
from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)


class CampusNavigator:
    """Graph-based campus navigation engine."""

    def __init__(self, map_path: str):
        self.graph = nx.Graph()
        self.node_data = {}
        self.edge_directions = {}
        self._name_index: dict[str, str] = {}  # lowercase_name -> node_id
        self._load_map(map_path)
        self._validate_graph()
        self._build_name_index()

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

    def _validate_graph(self):
        """Validate graph integrity after loading. Logs warnings only, never raises."""
        # Check that every node has at least a "name" attribute
        for node_id in self.graph.nodes:
            attrs = self.node_data.get(node_id, {})
            if "name" not in attrs:
                logger.warning(
                    "Node '%s' is missing a 'name' attribute", node_id
                )

        # Check graph connectivity
        if len(self.graph.nodes) > 0:
            if not nx.is_connected(self.graph):
                components = list(nx.connected_components(self.graph))
                component_strs = [
                    "{" + ", ".join(sorted(c)) + "}" for c in components
                ]
                logger.warning(
                    "Campus graph is disconnected. Found %d components: %s",
                    len(components),
                    ", ".join(component_strs),
                )

        # Check all edge endpoints reference existing nodes
        for src, dst in self.edge_directions:
            if src not in self.graph:
                logger.warning(
                    "Edge direction references non-existent source node '%s'",
                    src,
                )
            if dst not in self.graph:
                logger.warning(
                    "Edge direction references non-existent destination node '%s'",
                    dst,
                )

    def _build_name_index(self):
        """Build a lowercase name -> node_id index for O(1) exact lookups."""
        for node_id, attrs in self.node_data.items():
            name = attrs.get("name", "")
            if name:
                self._name_index[name.lower()] = node_id

    def find_shortest_path(self, source: str, destination: str) -> dict:
        """
        Find shortest path using Dijkstra's algorithm.

        Always returns a dict:
          Success: {"ok": True, "path": [...], "total_distance": ...,
                    "directions": [...], "steps": [...]}
          Failure (invalid node): {"ok": False, "error_type": "invalid_source"
                    or "invalid_destination", "message": "...",
                    "suggestion": "nearest_node_name_or_None"}
          Failure (no path): {"ok": False, "error_type": "no_path",
                    "message": "..."}
        """
        if source not in self.graph:
            suggestion = self.find_nearest_node_by_name(source)
            suggestion_name = (
                self.get_node_name(suggestion) if suggestion else None
            )
            return {
                "ok": False,
                "error_type": "invalid_source",
                "message": f"Source node '{source}' not found in the campus map.",
                "suggestion": suggestion_name,
            }

        if destination not in self.graph:
            suggestion = self.find_nearest_node_by_name(destination)
            suggestion_name = (
                self.get_node_name(suggestion) if suggestion else None
            )
            return {
                "ok": False,
                "error_type": "invalid_destination",
                "message": f"Destination node '{destination}' not found in the campus map.",
                "suggestion": suggestion_name,
            }

        try:
            path = nx.dijkstra_path(
                self.graph, source, destination, weight="weight"
            )
            total_distance = nx.dijkstra_path_length(
                self.graph, source, destination, weight="weight"
            )
        except nx.NetworkXNoPath:
            return {
                "ok": False,
                "error_type": "no_path",
                "message": (
                    f"No path exists between "
                    f"'{self.get_node_name(source)}' and "
                    f"'{self.get_node_name(destination)}'."
                ),
            }

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
            "ok": True,
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
        if not result.get("ok"):
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
        """
        Find a node ID by name lookup with cascading strategy:
          1. Exact match (O(1) via index)
          2. Substring match (O(n))
          3. Fuzzy match via fuzz.partial_ratio (O(n), threshold 70)

        Returns the best matching node_id, or None if no match found.
        """
        name_lower = name.lower()

        # 1. Exact match via index
        if name_lower in self._name_index:
            return self._name_index[name_lower]

        # 2. Substring match — collect all matches, pick the best (shortest name
        #    that contains the query, which is the most specific match)
        substring_matches = []
        for indexed_name, node_id in self._name_index.items():
            if name_lower in indexed_name or indexed_name in name_lower:
                substring_matches.append((node_id, indexed_name))

        if substring_matches:
            # Prefer the match whose name is closest in length to the query
            best = min(
                substring_matches,
                key=lambda pair: abs(len(pair[1]) - len(name_lower)),
            )
            return best[0]

        # 3. Fuzzy match — find the best score above threshold
        best_score = 0
        best_node_id = None
        for indexed_name, node_id in self._name_index.items():
            score = fuzz.partial_ratio(name_lower, indexed_name)
            if score > best_score:
                best_score = score
                best_node_id = node_id

        if best_score >= 70:
            return best_node_id

        return None
