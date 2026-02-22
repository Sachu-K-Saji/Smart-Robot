"""
Intent classification and entity extraction using regex patterns
and fuzzywuzzy fuzzy string matching.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from fuzzywuzzy import fuzz


@dataclass
class ParsedIntent:
    """Result of intent parsing."""
    intent: str       # navigation, faculty_info, student_lookup,
                      # department_info, campus_info, greeting,
                      # farewell, help, unknown
    confidence: float  # 0.0 to 1.0
    entities: dict = field(default_factory=dict)
    raw_text: str = ""


class IntentParser:
    """
    Classify user intent and extract entities from transcribed speech.
    Uses regex patterns for intent type, fuzzywuzzy for entity matching.
    """

    INTENT_PATTERNS = [
        # Navigation
        (
            "navigation",
            re.compile(
                r"\b(how\s+(?:do\s+i\s+)?(?:get|go|reach|find|walk|navigate)"
                r"|where\s+is|take\s+me\s+to|directions?\s+to"
                r"|way\s+to|route\s+to|path\s+to"
                r"|i\s+(?:want|need)\s+to\s+(?:go|get|reach|find))\b",
                re.IGNORECASE,
            ),
        ),
        # Faculty info
        (
            "faculty_info",
            re.compile(
                r"\b(who\s+is\s+(?:dr|prof|professor|doctor)"
                r"|faculty|professor|teacher|staff"
                r"|(?:dr|prof)\s*\.?\s*\w+"
                r"|office\s+(?:of|location|hours)"
                r"|hod|head\s+of\s+department)\b",
                re.IGNORECASE,
            ),
        ),
        # Student lookup
        (
            "student_lookup",
            re.compile(
                r"\b(student|roll\s*number|which\s+(?:class|section|year)"
                r"|enroll|belongs?\s+to)\b",
                re.IGNORECASE,
            ),
        ),
        # Department info
        (
            "department_info",
            re.compile(
                r"\b(department|(?:computer\s+science|ece|mechanical|civil|it"
                r"|electrical|electronics|management|mca|bca|commerce"
                r"|english|hindi|malayalam|hotel\s+management"
                r"|applied\s+science|humanities)"
                r"\s*(?:department|dept)?"
                r"|what\s+departments?"
                r"|which\s+college)\b",
                re.IGNORECASE,
            ),
        ),
        # Campus info — general questions about campus life and facilities
        (
            "campus_info",
            re.compile(
                r"\b(tell\s+me\s+about"
                r"|(?:what|where)\s+(?:is|are)\s+the"
                r"|information\s+(?:about|on|regarding)"
                r"|do\s+you\s+have\s+(?:a\s+)?"
                r"|is\s+there\s+(?:a\s+|any\s+)?"
                r"|about\s+the"
                r"|hostel|library|admission|placement|canteen|cafeteria"
                r"|sports|lab|club|committee|seminar|workshop"
                r"|history|vision|mission|course|programme|program"
                r"|scholarship|fees?|facility|facilities|auditorium"
                r"|transportation|bus|nss|ncc)\b",
                re.IGNORECASE,
            ),
        ),
        # Greeting
        (
            "greeting",
            re.compile(
                r"\b(hello|hi|hey|good\s+(?:morning|afternoon|evening)"
                r"|greetings|howdy|what'?s?\s+up)\b",
                re.IGNORECASE,
            ),
        ),
        # Farewell
        (
            "farewell",
            re.compile(
                r"\b(bye|goodbye|see\s+you|thank(?:s|\s+you)|that'?s?\s+all"
                r"|done|no\s+more\s+questions)\b",
                re.IGNORECASE,
            ),
        ),
        # Help
        (
            "help",
            re.compile(
                r"\b(help|what\s+can\s+you\s+do|options|menu"
                r"|capabilities|features)\b",
                re.IGNORECASE,
            ),
        ),
    ]

    def __init__(
        self,
        location_names: list[str],
        faculty_names: list[str],
        department_names: list[str],
        fuzzy_threshold: int = 70,
    ):
        self.location_names = location_names
        self.faculty_names = faculty_names
        self.department_names = department_names
        self.fuzzy_threshold = fuzzy_threshold

    def parse(self, text: str) -> ParsedIntent:
        """Parse transcribed text into intent + entities."""
        text = text.strip()
        if not text:
            return ParsedIntent(intent="unknown", confidence=0.0, raw_text=text)

        # Step 1: Classify intent via regex
        intent = "unknown"
        confidence = 0.0
        for intent_name, pattern in self.INTENT_PATTERNS:
            if pattern.search(text):
                intent = intent_name
                confidence = 0.85
                break

        # Step 2: Extract entities via fuzzy matching
        entities = {}

        loc_match = self._best_fuzzy_match(text, self.location_names)
        if loc_match:
            entities["location"] = loc_match[0]
            entities["location_score"] = loc_match[1]

        fac_match = self._best_fuzzy_match(text, self.faculty_names)
        if fac_match:
            entities["faculty_name"] = fac_match[0]
            entities["faculty_score"] = fac_match[1]

        dept_match = self._best_fuzzy_match(text, self.department_names)
        if dept_match:
            entities["department_name"] = dept_match[0]
            entities["department_score"] = dept_match[1]

        # Step 3: If no regex matched but we found entities, infer intent
        if intent == "unknown" and entities:
            if "location" in entities:
                intent = "navigation"
                confidence = entities["location_score"] / 100.0
            elif "faculty_name" in entities:
                intent = "faculty_info"
                confidence = entities["faculty_score"] / 100.0
            elif "department_name" in entities:
                intent = "department_info"
                confidence = entities["department_score"] / 100.0

        return ParsedIntent(
            intent=intent,
            confidence=confidence,
            entities=entities,
            raw_text=text,
        )

    def _best_fuzzy_match(
        self, text: str, candidates: list[str]
    ) -> Optional[tuple[str, int]]:
        """Find the best fuzzy match for any candidate within the text."""
        best_candidate = None
        best_score = 0

        for candidate in candidates:
            score = fuzz.partial_ratio(text.lower(), candidate.lower())
            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_score >= self.fuzzy_threshold:
            return (best_candidate, best_score)
        return None
