"""
Chat API Endpoint for Trace

Python endpoint for chat queries. Orchestrates retrieval, graph expansion,
aggregates lookup, and answer synthesis.

P7-06: Chat API endpoint
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.chat.prompts.answer import AnswerSynthesizer, Citation
from src.core.paths import DB_PATH
from src.retrieval.aggregates import AggregateItem, AggregatesLookup
from src.retrieval.graph import GraphExpander, RelatedEntity
from src.retrieval.search import NoteMatch, VectorSearcher
from src.retrieval.time import TimeFilter, parse_time_filter

logger = logging.getLogger(__name__)


@dataclass
class ChatRequest:
    """A chat request from the user."""

    query: str
    time_filter_hint: str | None = None  # Optional explicit time filter
    include_graph_expansion: bool = True
    include_aggregates: bool = True
    max_results: int = 10


@dataclass
class ChatResponse:
    """A chat response to the user."""

    answer: str
    citations: list[Citation]
    notes: list[NoteMatch]
    time_filter: TimeFilter | None
    related_entities: list[RelatedEntity]
    aggregates: list[AggregateItem]
    query_type: str
    confidence: float
    processing_time_ms: float

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "notes": [n.to_dict() for n in self.notes],
            "time_filter": self.time_filter.to_dict() if self.time_filter else None,
            "related_entities": [e.to_dict() for e in self.related_entities],
            "aggregates": [a.to_dict() for a in self.aggregates],
            "query_type": self.query_type,
            "confidence": self.confidence,
            "processing_time_ms": self.processing_time_ms,
        }


class ChatAPI:
    """
    Main chat API for Trace.

    Orchestrates:
    1. Time filter parsing
    2. Vector search
    3. Graph expansion
    4. Aggregates lookup
    5. Answer synthesis
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the chat API.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._api_key = api_key

        # Initialize components
        self._searcher = VectorSearcher(db_path=self.db_path, api_key=api_key)
        self._expander = GraphExpander(db_path=self.db_path)
        self._aggregates = AggregatesLookup(db_path=self.db_path)
        self._synthesizer = AnswerSynthesizer(api_key=api_key)

    def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Process a chat request and return a response.

        Args:
            request: ChatRequest with user query

        Returns:
            ChatResponse with answer and supporting data
        """
        import time

        start_time = time.time()

        # Parse time filter from query
        time_filter = None
        if request.time_filter_hint:
            time_filter = parse_time_filter(request.time_filter_hint)
        if time_filter is None:
            time_filter = parse_time_filter(request.query)

        # Detect query type
        query_type = self._detect_query_type(request.query)

        # Route based on query type
        if query_type == "aggregates":
            response = self._handle_aggregates_query(request, time_filter)
        elif query_type == "entity":
            response = self._handle_entity_query(request, time_filter)
        elif query_type == "timeline":
            response = self._handle_timeline_query(request, time_filter)
        else:
            response = self._handle_semantic_query(request, time_filter)

        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000

        return ChatResponse(
            answer=response["answer"],
            citations=response["citations"],
            notes=response["notes"],
            time_filter=time_filter,
            related_entities=response["related_entities"],
            aggregates=response["aggregates"],
            query_type=query_type,
            confidence=response["confidence"],
            processing_time_ms=processing_time,
        )

    def _detect_query_type(
        self, query: str
    ) -> Literal["aggregates", "entity", "timeline", "semantic"]:
        """
        Detect the type of query.

        Args:
            query: User query

        Returns:
            Query type string
        """
        query_lower = query.lower()

        # Check for aggregates (most/top) queries
        if self._aggregates.detect_most_query(query):
            return "aggregates"

        # Check for entity-specific queries
        entity_patterns = [
            "about ",
            "related to ",
            "involving ",
            "what do I know about ",
            "tell me about ",
        ]
        for pattern in entity_patterns:
            if pattern in query_lower:
                return "entity"

        # Check for timeline queries
        timeline_patterns = [
            "what did i do",
            "what was i doing",
            "summary of",
            "overview of",
            "activities ",
            "timeline ",
        ]
        for pattern in timeline_patterns:
            if pattern in query_lower:
                return "timeline"

        # Default to semantic search
        return "semantic"

    def _handle_aggregates_query(
        self,
        request: ChatRequest,
        time_filter: TimeFilter | None,
    ) -> dict:
        """Handle queries about aggregates (most/top)."""
        # Detect the key type from the query
        detected = self._aggregates.detect_most_query(request.query)

        if detected:
            _, key_type = detected
        else:
            key_type = "app"

        # Get aggregates
        result = self._aggregates.get_top_by_key_type(
            key_type, time_filter, limit=request.max_results
        )

        # Get related notes for context
        notes = []
        if result.items:
            # Search for notes related to the top items
            top_item = result.items[0]
            notes = self._searcher.search_by_entity(top_item.key, time_filter=time_filter, limit=5)

        # Synthesize answer
        synthesized = self._synthesizer.synthesize(
            question=request.query,
            notes=notes,
            time_filter=time_filter,
            aggregates=result.items,
        )

        return {
            "answer": synthesized.answer,
            "citations": synthesized.citations,
            "notes": notes,
            "related_entities": [],
            "aggregates": result.items,
            "confidence": synthesized.confidence,
        }

    def _handle_entity_query(
        self,
        request: ChatRequest,
        time_filter: TimeFilter | None,
    ) -> dict:
        """Handle queries about specific entities."""
        # Extract entity name from query
        entity_name = self._extract_entity_from_query(request.query)

        if not entity_name:
            return self._handle_semantic_query(request, time_filter)

        # Get entity context
        context = self._expander.get_entity_context(entity_name, time_filter=time_filter)

        if "error" in context:
            return self._handle_semantic_query(request, time_filter)

        # Get notes mentioning this entity
        notes = self._searcher.search_by_entity(
            entity_name, time_filter=time_filter, limit=request.max_results
        )

        # Build related entities list
        related_entities = []
        for rel in context.get("relationships", {}).get("outgoing", []):
            entity_info = rel["entity"]
            related_entities.append(
                RelatedEntity(
                    entity_id=entity_info["entity_id"],
                    entity_type=entity_info["entity_type"],
                    canonical_name=entity_info["canonical_name"],
                    edge_type=rel["edge_type"],
                    weight=rel["weight"],
                    source_entity_id="",
                    source_entity_name=entity_name,
                    direction="to",
                )
            )

        # Get aggregates for this entity
        agg_result = self._aggregates.get_time_for_key(entity_name, time_filter=time_filter)

        # Synthesize answer
        synthesized = self._synthesizer.synthesize(
            question=request.query,
            notes=notes,
            time_filter=time_filter,
            aggregates=agg_result.items,
            related_entities=related_entities,
        )

        return {
            "answer": synthesized.answer,
            "citations": synthesized.citations,
            "notes": notes,
            "related_entities": related_entities,
            "aggregates": agg_result.items,
            "confidence": synthesized.confidence,
        }

    def _handle_timeline_query(
        self,
        request: ChatRequest,
        time_filter: TimeFilter | None,
    ) -> dict:
        """Handle queries asking about activities in a time period."""
        # If no time filter, default to today
        if time_filter is None:
            time_filter = parse_time_filter("today")

        # Get all notes in the time range
        notes = self._searcher.get_notes_in_range(
            time_filter,
            limit=request.max_results,  # type: ignore
        )

        # Get aggregates for the period
        aggregates = []
        if time_filter:
            summary = self._aggregates.get_summary_for_period(time_filter)
            # Convert to AggregateItem list
            for key_type, data in summary.items():
                for item in data.get("top_items", []):
                    aggregates.append(
                        AggregateItem(
                            key=item["key"],
                            key_type=key_type,
                            value=item["minutes"],
                            period_type="custom",
                            period_start=time_filter.start,
                            period_end=time_filter.end,
                        )
                    )

        # Synthesize answer
        synthesized = self._synthesizer.synthesize(
            question=request.query,
            notes=notes,
            time_filter=time_filter,
            aggregates=aggregates[:10],
        )

        return {
            "answer": synthesized.answer,
            "citations": synthesized.citations,
            "notes": notes,
            "related_entities": [],
            "aggregates": aggregates[:10],
            "confidence": synthesized.confidence,
        }

    def _handle_semantic_query(
        self,
        request: ChatRequest,
        time_filter: TimeFilter | None,
    ) -> dict:
        """Handle general semantic search queries."""
        # Perform vector search
        search_result = self._searcher.search(
            query=request.query,
            time_filter=time_filter,
            limit=request.max_results,
        )

        notes = search_result.matches
        related_entities = []
        aggregates: list[AggregateItem] = []

        # Expand graph if requested and we have results
        if request.include_graph_expansion and notes:
            # Extract entity IDs from notes
            entity_ids = []
            conn = None
            try:
                conn = self._get_connection()
                for note in notes[:3]:  # Expand from top 3 notes
                    for entity in note.entities:
                        # Get entity ID from database
                        entity_name = entity.get("name", "")
                        entity_type = entity.get("type", "")
                        if entity_name:
                            # Find entity ID using GraphExpander's internal method
                            ids = self._expander._find_entity_ids_by_name(
                                conn,
                                entity_name,
                                entity_type,
                            )
                            entity_ids.extend(ids)
            finally:
                self._close_connection()

            if entity_ids:
                expansion = self._expander.expand_from_entities(
                    list(set(entity_ids))[:5],  # Limit seed entities
                    hops=1,
                    time_filter=time_filter,
                )
                related_entities = expansion.related_entities

        # Get aggregates if requested
        if request.include_aggregates and time_filter:
            summary = self._aggregates.get_summary_for_period(time_filter)
            for key_type, data in summary.items():
                for item in data.get("top_items", [])[:2]:  # Top 2 per category
                    aggregates.append(
                        AggregateItem(
                            key=item["key"],
                            key_type=key_type,
                            value=item["minutes"],
                            period_type="custom",
                            period_start=time_filter.start,
                            period_end=time_filter.end,
                        )
                    )

        # Synthesize answer
        if notes:
            synthesized = self._synthesizer.synthesize(
                question=request.query,
                notes=notes,
                time_filter=time_filter,
                aggregates=aggregates,
                related_entities=related_entities,
            )
        else:
            synthesized = self._synthesizer.synthesize_without_context(request.query)

        return {
            "answer": synthesized.answer,
            "citations": synthesized.citations,
            "notes": notes,
            "related_entities": related_entities,
            "aggregates": aggregates,
            "confidence": synthesized.confidence,
        }

    def _extract_entity_from_query(self, query: str) -> str | None:
        """Extract an entity name from a query."""
        import re

        patterns = [
            r"about\s+[\"']?([^\"'?]+)[\"']?",
            r"related to\s+[\"']?([^\"'?]+)[\"']?",
            r"involving\s+[\"']?([^\"'?]+)[\"']?",
            r"what do i know about\s+[\"']?([^\"'?]+)[\"']?",
            r"tell me about\s+[\"']?([^\"'?]+)[\"']?",
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                entity = match.group(1).strip()
                # Clean up common trailing words
                entity = re.sub(r"\s*(today|yesterday|this week|last week).*$", "", entity)
                return entity if entity else None

        return None

    def _get_connection(self):
        """Get a database connection."""
        from src.db.migrations import get_connection

        if not hasattr(self, "_conn") or self._conn is None:
            self._conn = get_connection(self.db_path)
        return self._conn

    def _close_connection(self):
        """Close the database connection."""
        if hasattr(self, "_conn") and self._conn:
            self._conn.close()
            self._conn = None

    def query(self, query: str, time_filter: str | None = None) -> ChatResponse:
        """
        Simple query interface.

        Args:
            query: User's question
            time_filter: Optional time filter string (e.g., "today", "last week")

        Returns:
            ChatResponse
        """
        request = ChatRequest(
            query=query,
            time_filter_hint=time_filter,
        )
        return self.chat(request)


# Create a global instance for simple usage
_api_instance: ChatAPI | None = None


def get_chat_api(
    db_path: Path | str | None = None,
    api_key: str | None = None,
) -> ChatAPI:
    """
    Get the global chat API instance.

    Args:
        db_path: Optional database path override
        api_key: Optional API key override

    Returns:
        ChatAPI instance
    """
    global _api_instance

    if _api_instance is None or db_path or api_key:
        _api_instance = ChatAPI(db_path=db_path, api_key=api_key)

    return _api_instance


if __name__ == "__main__":
    import fire

    def chat(query: str, time_filter: str | None = None, db_path: str | None = None):
        """
        Send a chat query.

        Args:
            query: The question to ask
            time_filter: Optional time filter (e.g., "today", "last week")
            db_path: Optional database path
        """
        api = ChatAPI(db_path=db_path)
        response = api.query(query, time_filter)
        return response.to_dict()

    def interactive(db_path: str | None = None):
        """
        Start an interactive chat session.

        Args:
            db_path: Optional database path
        """
        api = ChatAPI(db_path=db_path)

        print("Trace Chat - Ask questions about your digital activity")
        print("Type 'quit' to exit, 'help' for tips")
        print("-" * 50)

        while True:
            try:
                query = input("\nYou: ").strip()

                if not query:
                    continue

                if query.lower() == "quit":
                    print("Goodbye!")
                    break

                if query.lower() == "help":
                    print(
                        """
Tips for asking questions:
- Include time context: "What did I do today?", "Last week's activities"
- Ask about specific topics: "Tell me about Python"
- Ask for rankings: "What were my most used apps this week?"
- Ask about patterns: "What topics have I been focusing on?"
                    """
                    )
                    continue

                response = api.query(query)
                print(f"\nTrace: {response.answer}")

                if response.citations:
                    print(f"\n[Based on {len(response.citations)} note(s)]")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")

    fire.Fire(
        {
            "chat": chat,
            "interactive": interactive,
        }
    )
