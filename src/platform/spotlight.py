"""
macOS Spotlight Integration

Enables Trace notes to be searchable via macOS Spotlight.
Uses extended attributes (xattr) to set Spotlight metadata.

P11-01: Spotlight integration
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def set_spotlight_metadata(
    file_path: str | Path,
    title: str | None = None,
    authors: list[str] | None = None,
    keywords: list[str] | None = None,
    description: str | None = None,
    content_type: str = "public.plain-text",
) -> bool:
    """
    Set Spotlight metadata on a file using xattr.

    Args:
        file_path: Path to the file
        title: Display title for the file
        authors: List of author names
        keywords: List of keywords/tags
        description: Brief description/summary
        content_type: UTI content type

    Returns:
        True if successful, False otherwise
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.warning(f"File not found for Spotlight metadata: {file_path}")
        return False

    try:
        # Set kMDItemTitle
        if title:
            _set_xattr(file_path, "com.apple.metadata:kMDItemTitle", title)

        # Set kMDItemAuthors
        if authors:
            _set_xattr_list(file_path, "com.apple.metadata:kMDItemAuthors", authors)

        # Set kMDItemKeywords
        if keywords:
            _set_xattr_list(file_path, "com.apple.metadata:kMDItemKeywords", keywords)

        # Set kMDItemDescription
        if description:
            _set_xattr(file_path, "com.apple.metadata:kMDItemDescription", description)

        # Set content type
        _set_xattr(file_path, "com.apple.metadata:kMDItemContentType", content_type)

        # Set kMDItemCreator to Trace
        _set_xattr(file_path, "com.apple.metadata:kMDItemCreator", "Trace")

        return True

    except Exception as e:
        logger.error(f"Failed to set Spotlight metadata for {file_path}: {e}")
        return False


def _set_xattr(file_path: Path, attr_name: str, value: str) -> None:
    """Set a string extended attribute using xattr command."""
    # Use plist format for Spotlight metadata
    plist_value = _to_plist_string(value)
    subprocess.run(
        ["xattr", "-w", attr_name, plist_value, str(file_path)],
        check=True,
        capture_output=True,
    )


def _set_xattr_list(file_path: Path, attr_name: str, values: list[str]) -> None:
    """Set a list extended attribute using xattr command."""
    plist_value = _to_plist_array(values)
    subprocess.run(
        ["xattr", "-w", attr_name, plist_value, str(file_path)],
        check=True,
        capture_output=True,
    )


def _to_plist_string(value: str) -> str:
    """Convert a string to plist binary format (base64 encoded)."""
    import plistlib

    plist_data = plistlib.dumps(value, fmt=plistlib.FMT_BINARY)
    import base64

    return base64.b64encode(plist_data).decode("ascii")


def _to_plist_array(values: list[str]) -> str:
    """Convert a list to plist binary format (base64 encoded)."""
    import plistlib

    plist_data = plistlib.dumps(values, fmt=plistlib.FMT_BINARY)
    import base64

    return base64.b64encode(plist_data).decode("ascii")


def index_note_for_spotlight(
    note_path: str | Path,
    title: str | None = None,
    summary: str | None = None,
    entities: list[str] | None = None,
    timestamp: datetime | None = None,
) -> bool:
    """
    Index a Trace note for Spotlight search.

    Args:
        note_path: Path to the markdown note file
        title: Note title (extracted from filename if not provided)
        summary: Note summary for description
        entities: List of entities for keywords
        timestamp: Note timestamp

    Returns:
        True if successful
    """
    note_path = Path(note_path)

    if not note_path.exists():
        logger.warning(f"Note not found for Spotlight indexing: {note_path}")
        return False

    # Extract title from filename if not provided
    if not title:
        # hour-YYYYMMDD-HH.md -> "Hour YYYYMMDD HH"
        # day-YYYYMMDD.md -> "Day YYYYMMDD"
        stem = note_path.stem
        if stem.startswith("hour-"):
            parts = stem.replace("hour-", "").split("-")
            if len(parts) >= 2:
                title = f"Trace Hour: {parts[0]} {parts[1]}:00"
            else:
                title = f"Trace Hour: {stem}"
        elif stem.startswith("day-"):
            date_part = stem.replace("day-", "")
            title = f"Trace Day: {date_part}"
        else:
            title = f"Trace Note: {stem}"

    # Build keywords from entities
    keywords = ["trace", "activity", "notes"]
    if entities:
        keywords.extend(entities[:20])  # Limit to avoid excessive metadata

    # Truncate summary for description
    description = summary[:500] if summary else None

    return set_spotlight_metadata(
        file_path=note_path,
        title=title,
        authors=["Trace"],
        keywords=keywords,
        description=description,
        content_type="net.daringfireball.markdown",
    )


def reindex_all_notes(notes_dir: str | Path) -> dict:
    """
    Reindex all notes in the notes directory for Spotlight.

    Args:
        notes_dir: Path to the notes directory

    Returns:
        Dict with success count and error count
    """
    notes_dir = Path(notes_dir)
    success_count = 0
    error_count = 0

    if not notes_dir.exists():
        logger.warning(f"Notes directory not found: {notes_dir}")
        return {"success": 0, "errors": 0, "total": 0}

    # Find all markdown files
    for md_file in notes_dir.rglob("*.md"):
        try:
            if index_note_for_spotlight(md_file):
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f"Failed to index {md_file}: {e}")
            error_count += 1

    logger.info(f"Spotlight reindex complete: {success_count} success, {error_count} errors")

    return {
        "success": success_count,
        "errors": error_count,
        "total": success_count + error_count,
    }


def trigger_spotlight_reindex(directory: str | Path) -> bool:
    """
    Trigger Spotlight to reindex a directory using mdimport.

    Args:
        directory: Path to directory to reindex

    Returns:
        True if successful
    """
    directory = Path(directory)

    if not directory.exists():
        logger.warning(f"Directory not found for Spotlight reindex: {directory}")
        return False

    try:
        # Use mdimport to trigger Spotlight indexing
        result = subprocess.run(
            ["mdimport", "-r", str(directory)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"mdimport failed: {result.stderr}")
            return False

        logger.info(f"Triggered Spotlight reindex for: {directory}")
        return True

    except Exception as e:
        logger.error(f"Failed to trigger Spotlight reindex: {e}")
        return False


def get_spotlight_status(notes_dir: str | Path) -> dict:
    """
    Get Spotlight indexing status for notes directory.

    Args:
        notes_dir: Path to notes directory

    Returns:
        Dict with indexing status
    """
    notes_dir = Path(notes_dir)

    if not notes_dir.exists():
        return {
            "indexed": False,
            "notes_count": 0,
            "directory": str(notes_dir),
            "error": "Directory not found",
        }

    # Count notes
    notes_count = len(list(notes_dir.rglob("*.md")))

    # Check if directory is in Spotlight exclusions
    is_excluded = _is_spotlight_excluded(notes_dir)

    return {
        "indexed": not is_excluded,
        "notes_count": notes_count,
        "directory": str(notes_dir),
        "excluded": is_excluded,
    }


def _is_spotlight_excluded(directory: Path) -> bool:
    """Check if a directory is excluded from Spotlight indexing."""
    try:
        # Check for .metadata_never_index file
        if (directory / ".metadata_never_index").exists():
            return True

        # Use mdutil to check status
        result = subprocess.run(
            ["mdutil", "-s", str(directory)],
            capture_output=True,
            text=True,
        )

        # Parse output to check if indexing is enabled
        output = result.stdout.lower()
        if "indexing disabled" in output or "indexing enabled. (disabled)" in output:
            return True

        return False

    except Exception:
        return False


if __name__ == "__main__":
    import fire

    def index(notes_dir: str = "~/Library/Application Support/Trace/notes"):
        """Reindex all notes for Spotlight."""
        notes_path = Path(notes_dir).expanduser()
        result = reindex_all_notes(notes_path)
        print(f"Indexed {result['success']} notes, {result['errors']} errors")

    def status(notes_dir: str = "~/Library/Application Support/Trace/notes"):
        """Check Spotlight indexing status."""
        notes_path = Path(notes_dir).expanduser()
        status = get_spotlight_status(notes_path)
        print(f"Directory: {status['directory']}")
        print(f"Notes count: {status['notes_count']}")
        print(f"Indexed: {status['indexed']}")
        if status.get("excluded"):
            print("Warning: Directory is excluded from Spotlight")

    def reindex(notes_dir: str = "~/Library/Application Support/Trace/notes"):
        """Trigger Spotlight to reindex notes directory."""
        notes_path = Path(notes_dir).expanduser()
        if trigger_spotlight_reindex(notes_path):
            print(f"Triggered Spotlight reindex for: {notes_path}")
        else:
            print("Failed to trigger reindex")

    fire.Fire({"index": index, "status": status, "reindex": reindex})
