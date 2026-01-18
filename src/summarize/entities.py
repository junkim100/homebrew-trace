"""
Entity Extraction and Storage for Trace

Extracts entities from summaries and stores them in the database.
Handles normalization, deduplication, and note-entity associations.

Entity types:
- topic: Abstract subjects or concepts
- app: Applications
- domain: Web domains
- document: Files or documents
- artist: Musicians or content creators
- track: Specific songs or audio
- video: Videos or shows
- game: Games
- person: People
- project: Projects or work items

P5-07: Entity extraction and storage
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.summarize.schemas import EntityItem, HourlySummarySchema

logger = logging.getLogger(__name__)


@dataclass
class StoredEntity:
    """An entity stored in the database."""

    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str]
    created_ts: datetime
    updated_ts: datetime


@dataclass
class NoteEntityLink:
    """A link between a note and an entity."""

    note_id: str
    entity_id: str
    strength: float
    context: str | None


class EntityExtractor:
    """
    Extracts and stores entities from hourly summaries.

    Handles:
    - Entity extraction from validated summaries
    - Name normalization (case, whitespace)
    - Deduplication via canonical names
    - Note-entity association storage
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the entity extractor.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def extract_and_store(
        self,
        summary: HourlySummarySchema,
        note_id: str,
    ) -> list[NoteEntityLink]:
        """
        Extract entities from a summary and store them.

        Args:
            summary: Validated HourlySummarySchema
            note_id: ID of the note these entities are from

        Returns:
            List of created note-entity links
        """
        links = []

        conn = get_connection(self.db_path)
        try:
            # Extract entities from the summary
            entities = self._collect_entities(summary)

            for entity_item, context in entities:
                # Normalize and find/create entity
                entity_id = self._get_or_create_entity(
                    conn,
                    entity_type=entity_item.type,
                    name=entity_item.name,
                )

                # Create note-entity link
                link = self._create_note_entity_link(
                    conn,
                    note_id=note_id,
                    entity_id=entity_id,
                    strength=entity_item.confidence,
                    context=context,
                )
                if link:
                    links.append(link)

            conn.commit()
        except Exception as e:
            logger.error(f"Failed to extract and store entities: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

        return links

    def _collect_entities(
        self, summary: HourlySummarySchema
    ) -> list[tuple[EntityItem, str | None]]:
        """
        Collect all entities from a summary with context.

        Returns list of (EntityItem, context) tuples.
        """
        entities = []

        # Direct entities from summary
        for entity in summary.entities:
            entities.append((entity, None))

        # Entities from topics
        for topic in summary.topics:
            entity = EntityItem(
                name=topic.name,
                type="topic",
                confidence=topic.confidence,
            )
            entities.append((entity, topic.context))

        # Entities from media
        for listening in summary.media.listening:
            # Artist entity
            artist_entity = EntityItem(
                name=listening.artist,
                type="artist",
                confidence=0.9,
            )
            entities.append((artist_entity, f"Listening to {listening.track}"))

            # Track entity
            track_entity = EntityItem(
                name=f"{listening.artist} - {listening.track}",
                type="track",
                confidence=0.9,
            )
            entities.append((track_entity, None))

        for watching in summary.media.watching:
            video_entity = EntityItem(
                name=watching.title,
                type="video",
                confidence=0.85,
            )
            source_context = f"on {watching.source}" if watching.source else None
            entities.append((video_entity, source_context))

        # Entities from documents
        for doc in summary.documents:
            doc_entity = EntityItem(
                name=doc.name,
                type="document",
                confidence=0.9,
            )
            entities.append((doc_entity, doc.key_content))

        # Entities from websites
        for site in summary.websites:
            domain_entity = EntityItem(
                name=site.domain,
                type="domain",
                confidence=0.9,
            )
            entities.append((domain_entity, site.purpose))

        return entities

    def _get_or_create_entity(
        self,
        conn,
        entity_type: str,
        name: str,
    ) -> str:
        """
        Get existing entity or create new one.

        Args:
            conn: Database connection
            entity_type: Type of entity
            name: Entity name

        Returns:
            Entity ID
        """
        # Normalize name
        canonical_name = self._normalize_name(name)

        # Check for existing entity
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT entity_id, aliases
            FROM entities
            WHERE entity_type = ? AND canonical_name = ?
            """,
            (entity_type, canonical_name),
        )
        row = cursor.fetchone()

        if row:
            entity_id = row["entity_id"]

            # Update aliases if this is a new variation
            aliases = json.loads(row["aliases"]) if row["aliases"] else []
            if name != canonical_name and name not in aliases:
                aliases.append(name)
                cursor.execute(
                    """
                    UPDATE entities
                    SET aliases = ?, updated_ts = ?
                    WHERE entity_id = ?
                    """,
                    (json.dumps(aliases), datetime.now().isoformat(), entity_id),
                )

            return entity_id

        # Create new entity
        entity_id = str(uuid.uuid4())
        aliases = [name] if name != canonical_name else []

        cursor.execute(
            """
            INSERT INTO entities (entity_id, entity_type, canonical_name, aliases, created_ts, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                entity_type,
                canonical_name,
                json.dumps(aliases) if aliases else None,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )

        logger.debug(f"Created entity {entity_id}: {entity_type}/{canonical_name}")
        return entity_id

    def _create_note_entity_link(
        self,
        conn,
        note_id: str,
        entity_id: str,
        strength: float,
        context: str | None,
    ) -> NoteEntityLink | None:
        """
        Create a link between a note and an entity.

        Args:
            conn: Database connection
            note_id: Note ID
            entity_id: Entity ID
            strength: Association strength (0-1)
            context: Optional context about the association

        Returns:
            NoteEntityLink if created, None if already exists
        """
        cursor = conn.cursor()

        # Check for existing link
        cursor.execute(
            """
            SELECT note_id FROM note_entities
            WHERE note_id = ? AND entity_id = ?
            """,
            (note_id, entity_id),
        )

        if cursor.fetchone():
            # Update existing link if strength is higher
            cursor.execute(
                """
                UPDATE note_entities
                SET strength = MAX(strength, ?), context = COALESCE(?, context)
                WHERE note_id = ? AND entity_id = ?
                """,
                (strength, context, note_id, entity_id),
            )
            return None

        # Create new link
        cursor.execute(
            """
            INSERT INTO note_entities (note_id, entity_id, strength, context)
            VALUES (?, ?, ?, ?)
            """,
            (note_id, entity_id, strength, context),
        )

        return NoteEntityLink(
            note_id=note_id,
            entity_id=entity_id,
            strength=strength,
            context=context,
        )

    def _normalize_name(self, name: str) -> str:
        """
        Normalize an entity name for deduplication.

        - Lowercase
        - Trim whitespace
        - Collapse multiple spaces
        - Remove leading/trailing punctuation
        """
        # Lowercase
        normalized = name.lower()

        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Trim
        normalized = normalized.strip()

        # Remove leading/trailing punctuation (but keep internal)
        normalized = re.sub(r"^[^\w]+|[^\w]+$", "", normalized)

        return normalized

    def get_entity(self, entity_id: str) -> StoredEntity | None:
        """Get an entity by ID."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT entity_id, entity_type, canonical_name, aliases, created_ts, updated_ts
                FROM entities
                WHERE entity_id = ?
                """,
                (entity_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return StoredEntity(
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                canonical_name=row["canonical_name"],
                aliases=json.loads(row["aliases"]) if row["aliases"] else [],
                created_ts=datetime.fromisoformat(row["created_ts"]),
                updated_ts=datetime.fromisoformat(row["updated_ts"]),
            )
        finally:
            conn.close()

    def get_entities_for_note(self, note_id: str) -> list[tuple[StoredEntity, float]]:
        """Get all entities linked to a note with their strengths."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT e.entity_id, e.entity_type, e.canonical_name, e.aliases,
                       e.created_ts, e.updated_ts, ne.strength
                FROM entities e
                JOIN note_entities ne ON e.entity_id = ne.entity_id
                WHERE ne.note_id = ?
                ORDER BY ne.strength DESC
                """,
                (note_id,),
            )

            results = []
            for row in cursor.fetchall():
                entity = StoredEntity(
                    entity_id=row["entity_id"],
                    entity_type=row["entity_type"],
                    canonical_name=row["canonical_name"],
                    aliases=json.loads(row["aliases"]) if row["aliases"] else [],
                    created_ts=datetime.fromisoformat(row["created_ts"]),
                    updated_ts=datetime.fromisoformat(row["updated_ts"]),
                )
                results.append((entity, row["strength"]))

            return results
        finally:
            conn.close()

    def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[StoredEntity]:
        """
        Search entities by name.

        Args:
            query: Search query (matches canonical name or aliases)
            entity_type: Optional filter by type
            limit: Maximum results

        Returns:
            List of matching entities
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Normalize query
            normalized_query = self._normalize_name(query)
            like_pattern = f"%{normalized_query}%"

            if entity_type:
                cursor.execute(
                    """
                    SELECT entity_id, entity_type, canonical_name, aliases, created_ts, updated_ts
                    FROM entities
                    WHERE entity_type = ? AND (canonical_name LIKE ? OR aliases LIKE ?)
                    ORDER BY canonical_name
                    LIMIT ?
                    """,
                    (entity_type, like_pattern, like_pattern, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT entity_id, entity_type, canonical_name, aliases, created_ts, updated_ts
                    FROM entities
                    WHERE canonical_name LIKE ? OR aliases LIKE ?
                    ORDER BY canonical_name
                    LIMIT ?
                    """,
                    (like_pattern, like_pattern, limit),
                )

            results = []
            for row in cursor.fetchall():
                results.append(
                    StoredEntity(
                        entity_id=row["entity_id"],
                        entity_type=row["entity_type"],
                        canonical_name=row["canonical_name"],
                        aliases=json.loads(row["aliases"]) if row["aliases"] else [],
                        created_ts=datetime.fromisoformat(row["created_ts"]),
                        updated_ts=datetime.fromisoformat(row["updated_ts"]),
                    )
                )

            return results
        finally:
            conn.close()

    def get_entity_counts(self) -> dict[str, int]:
        """Get count of entities by type."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT entity_type, COUNT(*) as count
                FROM entities
                GROUP BY entity_type
                """
            )

            counts = {}
            for row in cursor.fetchall():
                counts[row["entity_type"]] = row["count"]

            return counts
        finally:
            conn.close()


if __name__ == "__main__":
    import fire

    def extract_demo():
        """Demo entity extraction from a sample summary."""
        from src.summarize.schemas import HourlySummarySchema

        # Create sample summary
        summary = HourlySummarySchema(
            schema_version=1,
            summary="The user worked on Python code and listened to music.",
            categories=["work", "entertainment"],
            activities=[],
            topics=[
                {"name": "Python programming", "context": "Writing async code", "confidence": 0.9}
            ],
            entities=[
                {"name": "VS Code", "type": "app", "confidence": 0.95},
                {"name": "GitHub", "type": "domain", "confidence": 0.9},
            ],
            media={
                "listening": [
                    {"artist": "Lofi Girl", "track": "Study Beats", "duration_seconds": 1800}
                ],
                "watching": [],
            },
            documents=[
                {"name": "async_guide.pdf", "type": "pdf", "key_content": "Asyncio patterns"}
            ],
            websites=[{"domain": "docs.python.org", "purpose": "Documentation"}],
            co_activities=[],
            open_loops=[],
            location=None,
        )

        extractor = EntityExtractor()
        entities = extractor._collect_entities(summary)

        return {
            "total_entities": len(entities),
            "entities": [
                {"name": e.name, "type": e.type, "confidence": e.confidence, "context": ctx}
                for e, ctx in entities
            ],
        }

    def search(query: str, entity_type: str | None = None):
        """Search for entities."""
        extractor = EntityExtractor()
        results = extractor.search_entities(query, entity_type)

        return [
            {
                "entity_id": e.entity_id,
                "type": e.entity_type,
                "name": e.canonical_name,
                "aliases": e.aliases,
            }
            for e in results
        ]

    def counts():
        """Get entity counts by type."""
        extractor = EntityExtractor()
        return extractor.get_entity_counts()

    fire.Fire({"demo": extract_demo, "search": search, "counts": counts})
