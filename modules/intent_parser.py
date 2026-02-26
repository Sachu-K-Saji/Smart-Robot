"""
Intent classification and entity extraction using regex patterns
and fuzzywuzzy fuzzy string matching.

Phase 5 enhancements:
- Multi-pattern scoring with specificity weights
- STT error compensation (common misrecognition corrections)
- Entity conflict resolution based on intent context
- Token-set-ratio false positive guard for short candidates
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from fuzzywuzzy import fuzz


# ── STT Error Compensation Tables ────────────────────────────────

STT_CORRECTIONS = {
    # ── Department acronyms ──
    "see us": "CS",
    "see yes": "CS",
    "see as": "CS",
    "see s": "CS",
    "c s": "CS",
    "easy": "ECE",
    "e c e": "ECE",
    "ee see ee": "ECE",
    "i tea": "IT",
    "eye tea": "IT",
    "i t": "IT",
    "emmy see hey": "MCA",
    "em see a": "MCA",
    "m c a": "MCA",
    "bee see hey": "BCA",
    "b c a": "BCA",
    "bee see a": "BCA",
    "em bee hey": "MBA",
    "m b a": "MBA",
    "bee tech": "B.Tech",
    "em tech": "M.Tech",
    # ── Titles and honorifics ──
    "doc": "Dr.",
    "doc to": "Doctor",
    "doc tar": "Doctor",
    "mister": "Mr.",
    "miss is": "Mrs.",
    "miss us": "Mrs.",
    # ── v/w confusion (common South Indian) ──
    "vhere": "where",
    "vhat": "what",
    "vhen": "when",
    "vhich": "which",
    "vho": "who",
    "vhy": "why",
    "vith": "with",
    "ve": "we",
    "vant": "want",
    "vork": "work",
    "vay": "way",
    # ── th/t and th/d substitution ──
    "tink": "think",
    "ting": "thing",
    "dat": "that",
    "dis": "this",
    "dere": "there",
    "dem": "them",
    "den": "then",
    "de": "the",
    "dey": "they",
    "wid": "with",
    "baat": "bath",
    "mout": "mouth",
    # ── Campus terms ──
    "liberry": "library",
    "libbary": "library",
    "hostle": "hostel",
    "hostall": "hostel",
    "affice": "office",
    "offis": "office",
    "can teen": "canteen",
    "kanteen": "canteen",
    "caffeteria": "cafeteria",
    "labortary": "laboratory",
    "labrotary": "laboratory",
    "auditoriyam": "auditorium",
    "semminar": "seminar",
    "placements": "placement",
    "admishun": "admission",
    "admishn": "admission",
    "depart meant": "department",
    "departmant": "department",
    "deparment": "department",
    "principel": "principal",
    "prinsiple": "principal",
    "prncipal": "principal",
    "professar": "professor",
    "profesar": "professor",
    # ── College name variants ──
    "lord's": "Lourdes",
    "lords": "Lourdes",
    "lourds": "Lourdes",
    "lowrdes": "Lourdes",
    "martha": "Matha",
    "mata": "Matha",
    "matta": "Matha",
    # ── Common Indian name garbles ──
    "raja sh": "Rajesh",
    "rajash": "Rajesh",
    "sure esh": "Suresh",
    "suresh": "Suresh",
    "pree ya": "Priya",
    "preya": "Priya",
    "sun ill": "Sunil",
    "suneel": "Sunil",
    "kumar": "Kumar",
    "koomar": "Kumar",
    "sharme": "Sharma",
    "sharmah": "Sharma",
}

# ── Phonetic Substitution Patterns ──────────────────────────
# Applied after word-level corrections.  Each entry is
# (regex_pattern, replacement, description).  Only applied when
# the result produces a word in KNOWN_VOCABULARY.

PHONETIC_SUBSTITUTIONS = [
    (r"\bvh", "wh", "v/w at word start"),
    (r"\bv(?=[aeiou])", "w", "v→w before vowel"),
    (r"shun\b", "tion", "-shun → -tion"),
    (r"mant\b", "ment", "-mant → -ment"),
    (r"shion\b", "sion", "-shion → -sion"),
    (r"\bd(?=is\b|at\b|ere\b|ey\b|em\b|en\b)", "th", "d→th before common suffixes"),
    (r"iy(?=am|um)\b", "ium", "-iyam/-iyum → -ium"),
]

# Vocabulary guard — phonetic subs only apply if result is a known word.
KNOWN_VOCABULARY = {
    "where", "what", "when", "which", "who", "why", "with",
    "want", "way", "work", "we", "will", "well", "were",
    "think", "thing", "that", "this", "there", "them", "then", "the", "they",
    "mention", "department", "placement", "admission", "auditorium",
    "navigation", "direction", "location", "information",
    "question", "session", "permission", "decision",
    "management", "assessment", "environment", "development",
}

ABBREVIATION_EXPANSIONS = {
    "cs": "Computer Science",
    "ece": "Electronics and Communication",
    "it": "Information Technology",
    "mca": "MCA",
    "bca": "BCA",
    "mech": "Mechanical",
}

# ── Intent Specificity Weights ───────────────────────────────────

INTENT_WEIGHTS = {
    "navigation": 0.90,
    "faculty_info": 0.90,
    "student_lookup": 0.85,
    "department_info": 0.85,
    "campus_info": 0.70,
    "greeting": 0.60,
    "farewell": 0.60,
    "help": 0.65,
}


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

    Multi-pattern scoring: all patterns are evaluated and scored with
    specificity weights. The highest-scoring intent wins.
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
                r"\b(who\s+is\s+(?:dr|prof|professor|doctor|the)"
                r"|faculty|professor|teacher|staff"
                r"|(?:dr|prof)\s*\.?\s*\w+"
                r"|office\s+(?:of|location|hours)"
                r"|hod|head\s+of\s+department"
                r"|principal|vice\s*-?\s*principal|dean|chairman|director)\b",
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
        raw_text = text.strip()
        if not raw_text:
            return ParsedIntent(intent="unknown", confidence=0.0, raw_text=raw_text)

        # Step 1: Preprocess for STT error compensation
        text = self._preprocess_text(raw_text)

        # Step 2: Multi-pattern intent scoring
        intent, confidence = self._score_intents(text)

        # Step 3: Extract entities via fuzzy matching
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

        # Step 4: If no regex matched but we found entities, infer intent
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

        # Step 5: Resolve entity conflicts based on intent context
        entities = self._resolve_entity_conflicts(intent, entities)

        return ParsedIntent(
            intent=intent,
            confidence=confidence,
            entities=entities,
            raw_text=raw_text,
        )

    # ── STT Preprocessing ────────────────────────────────────────

    def _preprocess_text(self, text: str) -> str:
        """Apply STT error corrections, phonetic substitutions, and
        abbreviation expansions.

        Order: STT corrections → phonetic substitutions → abbreviation expansions.
        """
        result = text

        # 1. Apply STT corrections (case-insensitive, word-boundary match)
        for wrong, correct in STT_CORRECTIONS.items():
            pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", re.IGNORECASE)
            result = pattern.sub(correct, result)

        # 2. Apply phonetic substitutions (only when result is a known word)
        result = self._apply_phonetic_subs(result)

        # 3. Expand standalone abbreviations (word-boundary match)
        for abbr, expansion in ABBREVIATION_EXPANSIONS.items():
            pattern = re.compile(r"\b" + re.escape(abbr) + r"\b", re.IGNORECASE)
            result = pattern.sub(expansion, result)

        return result

    @staticmethod
    def _apply_phonetic_subs(text: str) -> str:
        """Apply phonetic substitution patterns, only accepting changes
        that produce words in KNOWN_VOCABULARY."""
        words = text.split()
        result_words = []
        for word in words:
            best = word
            for pattern, replacement, _ in PHONETIC_SUBSTITUTIONS:
                candidate = re.sub(pattern, replacement, word, flags=re.IGNORECASE)
                if candidate.lower() != word.lower() and candidate.lower() in KNOWN_VOCABULARY:
                    best = candidate
                    break  # accept first matching substitution
            result_words.append(best)
        return " ".join(result_words)

    # ── Multi-Pattern Intent Scoring ─────────────────────────────

    def _score_intents(self, text: str) -> tuple[str, float]:
        """Score ALL matching patterns and return the highest-scoring intent.

        Confidence = base_weight * (0.7 + 0.3 * span_ratio)
        where span_ratio = len(match.group()) / len(text)
        """
        best_intent = "unknown"
        best_confidence = 0.0
        text_len = len(text)

        if text_len == 0:
            return best_intent, best_confidence

        for intent_name, pattern in self.INTENT_PATTERNS:
            match = pattern.search(text)
            if match:
                base_weight = INTENT_WEIGHTS.get(intent_name, 0.5)
                span_ratio = len(match.group()) / text_len
                confidence = base_weight * (0.7 + 0.3 * span_ratio)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_intent = intent_name

        return best_intent, best_confidence

    # ── Entity Conflict Resolution ───────────────────────────────

    def _resolve_entity_conflicts(
        self, intent: str, entities: dict
    ) -> dict:
        """Resolve conflicts when both location and department_name match.

        - navigation intent: keep location, drop department
        - department_info intent: keep department, drop location
        - otherwise: keep the higher-scoring entity
        """
        if "location" not in entities or "department_name" not in entities:
            return entities

        entities = dict(entities)  # shallow copy to avoid mutating caller's dict

        if intent == "navigation":
            del entities["department_name"]
            entities.pop("department_score", None)
        elif intent == "department_info":
            del entities["location"]
            entities.pop("location_score", None)
        else:
            loc_score = entities.get("location_score", 0)
            dept_score = entities.get("department_score", 0)
            if loc_score >= dept_score:
                del entities["department_name"]
                entities.pop("department_score", None)
            else:
                del entities["location"]
                entities.pop("location_score", None)

        return entities

    # ── Entity Grammar for Re-recognition ────────────────────────

    def get_entity_grammar(self, intent: str) -> list[str]:
        """Return a list of entity phrases to use as grammar constraints
        for two-pass re-recognition, based on intent type.
        """
        if intent == "navigation":
            return [name.lower() for name in self.location_names]
        elif intent == "faculty_info":
            return [name.lower() for name in self.faculty_names]
        elif intent in ("department_info", "campus_info"):
            return [name.lower() for name in self.department_names]
        elif intent == "student_lookup":
            return []  # student names are too dynamic for grammar
        return []

    # ── Fuzzy Matching ───────────────────────────────────────────

    def _best_fuzzy_match(
        self, text: str, candidates: list[str]
    ) -> Optional[tuple[str, int]]:
        """Find the best fuzzy match for any candidate within the text.

        Uses both full-text and token-based matching for better accuracy.
        Token-set-ratio is only used for candidates with 3+ tokens to
        prevent short names from producing false positives.
        """
        best_candidate = None
        best_score = 0
        text_lower = text.lower()

        for candidate in candidates:
            cand_lower = candidate.lower()
            # Direct substring check (best case)
            if cand_lower in text_lower:
                return (candidate, 100)

            # Standard partial ratio
            score = fuzz.partial_ratio(text_lower, cand_lower)

            # Only use token_set_ratio for candidates with 3+ tokens
            # to prevent short names from matching everything
            cand_token_count = len(cand_lower.split())
            if cand_token_count >= 3:
                token_score = fuzz.token_set_ratio(text_lower, cand_lower)
                score = max(score, token_score)

            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_score >= self.fuzzy_threshold:
            return (best_candidate, best_score)
        return None
