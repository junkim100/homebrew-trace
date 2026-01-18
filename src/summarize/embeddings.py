"""
Embedding Computation for Trace Notes

Computes embeddings for hourly notes using OpenAI's embedding API
and stores them via sqlite-vec for similarity search.

P5-08: Embedding computation
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.db.vectors import (
    delete_embedding,
    get_embedding_by_source,
    init_vector_table,
    load_sqlite_vec,
    store_embedding,
)
from src.summarize.schemas import HourlySummarySchema

logger = logging.getLogger(__name__)

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSIONS = 1536


@dataclass
class EmbeddingResult:
    """Result of embedding computation."""

    embedding_id: str
    source_type: str
    source_id: str
    dimensions: int
    model: str
    success: bool
    error: str | None = None


class EmbeddingComputer:
    """
    Computes and stores embeddings for notes.

    Uses OpenAI's text-embedding-3-small model and stores
    vectors via sqlite-vec for efficient similarity search.
    """

    def __init__(
        self,
        api_key: str | None = None,
        db_path: Path | str | None = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
    ):
        """
        Initialize the embedding computer.

        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            db_path: Path to SQLite database
            model: Embedding model name
            dimensions: Embedding dimensions
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client (lazy initialization)."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def compute_for_note(
        self,
        note_id: str,
        summary: HourlySummarySchema,
        hour_start: datetime | None = None,
    ) -> EmbeddingResult:
        """
        Compute and store embedding for a note.

        Args:
            note_id: ID of the note
            summary: Validated summary schema
            hour_start: Optional hour start time for context

        Returns:
            EmbeddingResult with status
        """
        # Build text for embedding
        text = self._build_embedding_text(summary, hour_start)

        # Compute embedding
        try:
            embedding = self._compute_embedding(text)
        except Exception as e:
            logger.error(f"Failed to compute embedding for note {note_id}: {e}")
            return EmbeddingResult(
                embedding_id="",
                source_type="note",
                source_id=note_id,
                dimensions=self.dimensions,
                model=self.model,
                success=False,
                error=str(e),
            )

        # Store embedding
        conn = get_connection(self.db_path)
        try:
            load_sqlite_vec(conn)
            init_vector_table(conn, self.dimensions)

            # Check for existing embedding and delete if present
            existing = get_embedding_by_source(conn, "note", note_id)
            if existing:
                delete_embedding(conn, existing["embedding_id"])
                logger.debug(f"Deleted existing embedding for note {note_id}")

            # Store new embedding
            embedding_id = store_embedding(
                conn,
                source_type="note",
                source_id=note_id,
                embedding=embedding,
                model_name=self.model,
            )

            # Update notes table with embedding_id
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE notes
                SET embedding_id = ?, updated_ts = ?
                WHERE note_id = ?
                """,
                (embedding_id, datetime.now().isoformat(), note_id),
            )
            conn.commit()

            logger.info(f"Computed and stored embedding {embedding_id} for note {note_id}")

            return EmbeddingResult(
                embedding_id=embedding_id,
                source_type="note",
                source_id=note_id,
                dimensions=self.dimensions,
                model=self.model,
                success=True,
            )

        except Exception as e:
            logger.error(f"Failed to store embedding for note {note_id}: {e}")
            conn.rollback()
            return EmbeddingResult(
                embedding_id="",
                source_type="note",
                source_id=note_id,
                dimensions=self.dimensions,
                model=self.model,
                success=False,
                error=str(e),
            )
        finally:
            conn.close()

    def compute_for_query(self, query: str) -> list[float] | None:
        """
        Compute embedding for a search query.

        Args:
            query: Search query text

        Returns:
            Embedding vector, or None on error
        """
        try:
            return self._compute_embedding(query)
        except Exception as e:
            logger.error(f"Failed to compute query embedding: {e}")
            return None

    def _build_embedding_text(
        self,
        summary: HourlySummarySchema,
        hour_start: datetime | None = None,
    ) -> str:
        """
        Build text representation of a summary for embedding.

        Creates a focused text that captures the key searchable content.
        """
        parts = []

        # Time context
        if hour_start:
            parts.append(f"Time: {hour_start.strftime('%A, %B %d, %Y at %H:00')}")

        # Summary
        parts.append(f"Summary: {summary.summary}")

        # Categories
        if summary.categories:
            parts.append(f"Categories: {', '.join(summary.categories)}")

        # Activities
        if summary.activities:
            activity_texts = []
            for act in summary.activities[:5]:  # Limit to top 5
                activity_texts.append(
                    f"{act.description} ({act.app})" if act.app else act.description
                )
            parts.append(f"Activities: {'; '.join(activity_texts)}")

        # Topics
        if summary.topics:
            topic_texts = [t.name for t in summary.topics]
            parts.append(f"Topics: {', '.join(topic_texts)}")

        # Entities
        if summary.entities:
            # Group by type
            by_type: dict[str, list[str]] = {}
            for entity in summary.entities:
                if entity.type not in by_type:
                    by_type[entity.type] = []
                by_type[entity.type].append(entity.name)

            for etype, names in by_type.items():
                parts.append(f"{etype.capitalize()}s: {', '.join(names)}")

        # Media
        if summary.media.listening:
            listening = [f"{item.artist} - {item.track}" for item in summary.media.listening]
            parts.append(f"Listening: {', '.join(listening)}")

        if summary.media.watching:
            watching = [item.title for item in summary.media.watching]
            parts.append(f"Watching: {', '.join(watching)}")

        # Documents
        if summary.documents:
            docs = [doc.name for doc in summary.documents]
            parts.append(f"Documents: {', '.join(docs)}")

        # Websites
        if summary.websites:
            sites = [site.domain for site in summary.websites]
            parts.append(f"Websites: {', '.join(sites)}")

        # Location
        if summary.location:
            parts.append(f"Location: {summary.location}")

        return "\n".join(parts)

    def _compute_embedding(self, text: str) -> list[float]:
        """
        Compute embedding for text using OpenAI API.

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            Exception: On API error
        """
        client = self._get_client()

        response = client.embeddings.create(
            input=text,
            model=self.model,
            dimensions=self.dimensions,
        )

        return response.data[0].embedding

    def recompute_for_note(self, note_id: str) -> EmbeddingResult:
        """
        Recompute embedding for an existing note.

        Loads the note's JSON payload from the database and recomputes.

        Args:
            note_id: ID of the note to recompute

        Returns:
            EmbeddingResult with status
        """
        import json

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, start_ts, json_payload
                FROM notes
                WHERE note_id = ?
                """,
                (note_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return EmbeddingResult(
                    embedding_id="",
                    source_type="note",
                    source_id=note_id,
                    dimensions=self.dimensions,
                    model=self.model,
                    success=False,
                    error="Note not found",
                )

            # Parse JSON payload
            try:
                payload = json.loads(row["json_payload"])
                summary = HourlySummarySchema.model_validate(payload)
            except Exception as e:
                return EmbeddingResult(
                    embedding_id="",
                    source_type="note",
                    source_id=note_id,
                    dimensions=self.dimensions,
                    model=self.model,
                    success=False,
                    error=f"Failed to parse note payload: {e}",
                )

            # Parse start time
            hour_start = None
            try:
                hour_start = datetime.fromisoformat(row["start_ts"])
            except (ValueError, TypeError):
                pass

        finally:
            conn.close()

        # Compute embedding
        return self.compute_for_note(note_id, summary, hour_start)


if __name__ == "__main__":
    import fire

    def compute(note_id: str, db_path: str | None = None):
        """Recompute embedding for a note."""
        computer = EmbeddingComputer(db_path=db_path)
        result = computer.recompute_for_note(note_id)

        return {
            "success": result.success,
            "embedding_id": result.embedding_id,
            "error": result.error,
            "model": result.model,
            "dimensions": result.dimensions,
        }

    def query(text: str):
        """Compute embedding for a query text."""
        computer = EmbeddingComputer()
        embedding = computer.compute_for_query(text)

        if embedding is None:
            return {"error": "Failed to compute embedding"}

        return {
            "dimensions": len(embedding),
            "embedding_preview": embedding[:5],  # First 5 values
        }

    def demo():
        """Demo with a sample summary."""
        summary = HourlySummarySchema(
            schema_version=1,
            summary="The user worked on Python code and listened to music.",
            categories=["work", "entertainment"],
            activities=[
                {
                    "time_start": "14:00",
                    "time_end": "15:00",
                    "description": "Writing Python code",
                    "app": "VS Code",
                    "category": "work",
                }
            ],
            topics=[{"name": "Python", "confidence": 0.9}],
            entities=[{"name": "VS Code", "type": "app", "confidence": 0.95}],
            media={
                "listening": [
                    {"artist": "Lofi Girl", "track": "Study Beats", "duration_seconds": 3600}
                ],
                "watching": [],
            },
            documents=[],
            websites=[],
            co_activities=[],
            open_loops=[],
            location=None,
        )

        computer = EmbeddingComputer()
        text = computer._build_embedding_text(summary, datetime(2025, 1, 15, 14, 0, 0))

        print("Embedding text:")
        print("-" * 40)
        print(text)
        print("-" * 40)

        # Compute actual embedding
        embedding = computer.compute_for_query(text)
        if embedding:
            print(f"\nEmbedding computed: {len(embedding)} dimensions")
            print(f"First 5 values: {embedding[:5]}")

    fire.Fire({"compute": compute, "query": query, "demo": demo})
