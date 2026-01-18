"""
Tests for the paths module.

Acceptance criteria for P1-06:
- Creates notes/, db/, cache/ directories on first run
"""

import os
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import pytest


class TestDataDirectories:
    """Test data directory creation and management."""

    def test_ensure_data_directories_creates_all_required_dirs(self, tmp_path: Path):
        """Test that ensure_data_directories creates all required directories."""
        # Override DATA_ROOT via environment variable
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            # Re-import to pick up the new DATA_ROOT
            import importlib

            from src.core import paths

            importlib.reload(paths)

            # Verify directories don't exist yet
            assert not (tmp_path / "notes").exists()
            assert not (tmp_path / "db").exists()
            assert not (tmp_path / "cache").exists()

            # Create directories
            results = paths.ensure_data_directories()

            # Verify all required directories were created
            assert (tmp_path / "notes").exists()
            assert (tmp_path / "db").exists()
            assert (tmp_path / "index").exists()
            assert (tmp_path / "cache").exists()
            assert (tmp_path / "cache" / "screenshots").exists()
            assert (tmp_path / "cache" / "text_buffers").exists()
            assert (tmp_path / "cache" / "ocr").exists()

            # Verify all were marked as created
            assert results["notes"] is True
            assert results["db"] is True
            assert results["cache"] is True

    def test_ensure_data_directories_is_idempotent(self, tmp_path: Path):
        """Test that ensure_data_directories can be called multiple times safely."""
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            import importlib

            from src.core import paths

            importlib.reload(paths)

            # First call creates
            results1 = paths.ensure_data_directories()
            created_count = sum(1 for v in results1.values() if v)
            assert created_count > 0

            # Second call is idempotent
            results2 = paths.ensure_data_directories()
            created_count2 = sum(1 for v in results2.values() if v)
            assert created_count2 == 0  # Nothing new created


class TestNotePaths:
    """Test note path generation."""

    def test_get_note_path_hourly(self, tmp_path: Path):
        """Test hourly note path generation."""
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            import importlib

            from src.core import paths

            importlib.reload(paths)

            dt = datetime(2024, 3, 15, 14, 30, 0)
            path = paths.get_note_path(dt, "hour")

            expected = tmp_path / "notes" / "2024" / "03" / "15" / "hour-20240315-14.md"
            assert path == expected

    def test_get_note_path_daily(self, tmp_path: Path):
        """Test daily note path generation."""
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            import importlib

            from src.core import paths

            importlib.reload(paths)

            d = date(2024, 3, 15)
            path = paths.get_note_path(d, "day")

            expected = tmp_path / "notes" / "2024" / "03" / "15" / "day-20240315.md"
            assert path == expected

    def test_get_note_path_invalid_type(self, tmp_path: Path):
        """Test that invalid note_type raises ValueError."""
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            import importlib

            from src.core import paths

            importlib.reload(paths)

            with pytest.raises(ValueError, match="note_type must be 'hour' or 'day'"):
                paths.get_note_path(datetime.now(), "invalid")


class TestCachePaths:
    """Test cache directory path generation."""

    def test_get_daily_cache_dirs(self, tmp_path: Path):
        """Test daily cache directory path generation."""
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            import importlib

            from src.core import paths

            importlib.reload(paths)

            d = date(2024, 3, 15)
            dirs = paths.get_daily_cache_dirs(d)

            assert dirs["screenshots"] == tmp_path / "cache" / "screenshots" / "20240315"
            assert dirs["text_buffers"] == tmp_path / "cache" / "text_buffers" / "20240315"
            assert dirs["ocr"] == tmp_path / "cache" / "ocr" / "20240315"

    def test_ensure_daily_cache_dirs(self, tmp_path: Path):
        """Test that ensure_daily_cache_dirs creates the directories."""
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            import importlib

            from src.core import paths

            importlib.reload(paths)

            # First ensure base directories exist
            paths.ensure_data_directories()

            d = date(2024, 3, 15)
            dirs = paths.ensure_daily_cache_dirs(d)

            # Verify directories were created
            assert dirs["screenshots"].exists()
            assert dirs["text_buffers"].exists()
            assert dirs["ocr"].exists()


class TestNoteDirectory:
    """Test note directory management."""

    def test_ensure_note_directory(self, tmp_path: Path):
        """Test that ensure_note_directory creates the correct path."""
        with mock.patch.dict(os.environ, {"TRACE_DATA_ROOT": str(tmp_path)}):
            import importlib

            from src.core import paths

            importlib.reload(paths)

            dt = datetime(2024, 3, 15, 14, 30)
            note_dir = paths.ensure_note_directory(dt)

            expected = tmp_path / "notes" / "2024" / "03" / "15"
            assert note_dir == expected
            assert note_dir.exists()
