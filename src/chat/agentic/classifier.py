"""
Query Complexity Classifier for Agentic Pipeline

Determines if a query needs agentic (multi-step) processing or can be
handled by simpler single-pass methods. Uses pattern matching and
heuristics for fast classification.
"""

import re
from typing import ClassVar

from src.chat.agentic.schemas import ClassificationResult, QueryType


class QueryClassifier:
    """
    Classifies queries by complexity to determine routing.

    Simple queries → existing ChatAPI handlers
    Complex queries → agentic planning and execution
    """

    # Pattern signals for different query types
    COMPLEXITY_SIGNALS: ClassVar[dict[QueryType, list[str]]] = {
        "relationship": [
            r"\bwhile\b.*\bwhat\b",
            r"\bwhen\b.*\bwhat\b",
            r"\bduring\b.*\bwhat\b",
            r"\balongside\b",
            r"\btogether with\b",
            r"\bat the same time\b",
            r"\blistening to\b.*\bwhile\b",
            r"\bwatching\b.*\bwhile\b",
            r"\bwhat.*\bwhen\b.*\bwas\b",
        ],
        "comparison": [
            r"\bcompare\b",
            r"\bvs\.?\b",
            r"\bversus\b",
            r"\bdifference\s+between\b",
            r"\bchanged\b.*\bover\b",
            r"\bhow\b.*\bchanged\b",
            r"\bfrom\b.*\bto\b.*\bperiod\b",
            r"\bjanuary\b.*\bvs\b",
            r"\blast\s+(?:week|month|year)\b.*\bthis\s+(?:week|month|year)\b",
        ],
        "memory_recall": [
            r"\bi\s+remember\b",
            r"\bthere\s+was\b.*\babout\b",
            r"\bsomething\s+about\b",
            r"\bwhat\s+was\s+it\b",
            r"\bwhat\s+did\s+i\s+learn\b",
            r"\bcan't\s+recall\b",
            r"\btrying\s+to\s+remember\b",
            r"\bwhat\s+was\s+the\b.*\bthat\b",
        ],
        "correlation": [
            r"\bpattern\b",
            r"\busually\b",
            r"\btend\s+to\b",
            r"\bafter\b.*\bdo\s+i\b",
            r"\bbefore\b.*\bdo\s+i\b",
            r"\btypically\b",
            r"\bwhat\s+do\s+i\s+(?:usually|typically)\b",
            r"\bis\s+there\s+a\s+(?:pattern|correlation)\b",
            r"\bhow\s+often\b",
        ],
        "web_augmented": [
            r"\blatest\b",
            r"\bcurrent\b.*\b(?:news|events|developments)\b",
            r"\brecent\s+news\b",
            r"\bsince\s+then\b",
            r"\bdevelopments\b",
            r"\bwhat\s+(?:is|are)\s+the\s+(?:latest|current)\b",
            r"\bwhat\s+happened\b.*\bworld\b",
            r"\bconnect\b.*\bwith\s+current\b",
        ],
        "multi_entity": [
            r"\bboth\b.*\band\b",
            r"\brelationship\s+between\b",
            r"\bhow\s+are\b.*\brelated\b",
            r"\bconnection\s+between\b",
            r"\b\w+\s+and\s+\w+\s+(?:together|related)\b",
        ],
    }

    # Minimum confidence to classify as complex
    COMPLEXITY_THRESHOLD = 0.4

    # Signals that indicate simple queries (override complexity)
    SIMPLE_SIGNALS: ClassVar[list[str]] = [
        r"^what\s+did\s+i\s+do\s+(?:today|yesterday|this\s+week)\??$",
        r"^(?:tell\s+me\s+)?about\s+\w+\??$",
        r"^what\s+(?:apps?|sites?|topics?)\b",
        r"^(?:most|top)\s+\w+\s+(?:apps?|sites?|topics?|artists?)\b",
        r"^summary\s+of\s+(?:today|yesterday|this\s+week)\b",
    ]

    def __init__(self) -> None:
        """Initialize the classifier with compiled regex patterns."""
        self._complexity_patterns: dict[QueryType, list[re.Pattern[str]]] = {}
        for query_type, patterns in self.COMPLEXITY_SIGNALS.items():
            self._complexity_patterns[query_type] = [re.compile(p, re.IGNORECASE) for p in patterns]

        self._simple_patterns = [re.compile(p, re.IGNORECASE) for p in self.SIMPLE_SIGNALS]

    def classify(self, query: str) -> ClassificationResult:
        """
        Classify a query's complexity and type.

        Args:
            query: The user's query string

        Returns:
            ClassificationResult with complexity decision and detected type
        """
        query = query.strip()

        # Check for simple query patterns first
        for pattern in self._simple_patterns:
            if pattern.search(query):
                return ClassificationResult(
                    is_complex=False,
                    query_type="simple",
                    confidence=0.9,
                    signals=["simple_pattern_match"],
                    reasoning="Query matches simple pattern, no agentic processing needed",
                )

        # Check for complexity signals
        detected_signals: list[str] = []
        type_scores: dict[QueryType, float] = {}

        for query_type, patterns in self._complexity_patterns.items():
            matches = 0
            for pattern in patterns:
                if pattern.search(query):
                    matches += 1
                    detected_signals.append(f"{query_type}:{pattern.pattern}")

            if matches > 0:
                # Score based on number of matching patterns
                type_scores[query_type] = min(1.0, matches * 0.4)

        if not type_scores:
            # No complexity signals detected
            return ClassificationResult(
                is_complex=False,
                query_type="simple",
                confidence=0.7,
                signals=[],
                reasoning="No complexity signals detected",
            )

        # Find the best matching query type
        best_type = max(type_scores, key=lambda k: type_scores[k])
        best_score = type_scores[best_type]

        is_complex = best_score >= self.COMPLEXITY_THRESHOLD

        # Build reasoning
        if is_complex:
            reasoning = f"Detected {best_type} query with {len(detected_signals)} signal(s)"
        else:
            reasoning = f"Low confidence ({best_score:.2f}) for {best_type} classification"

        return ClassificationResult(
            is_complex=is_complex,
            query_type=best_type if is_complex else "simple",
            confidence=best_score,
            signals=detected_signals[:5],  # Limit to top 5 signals
            reasoning=reasoning,
        )

    def is_complex(self, query: str) -> bool:
        """
        Quick check if a query needs agentic processing.

        Args:
            query: The user's query string

        Returns:
            True if the query should be handled by the agentic pipeline
        """
        return self.classify(query).is_complex

    def get_query_type(self, query: str) -> QueryType:
        """
        Get the detected query type.

        Args:
            query: The user's query string

        Returns:
            The detected query type
        """
        return self.classify(query).query_type
