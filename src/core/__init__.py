"""
Trace Core Module

This module provides core utilities including path management,
configuration, and common helpers for the Trace application.
"""

from .paths import (
    CACHE_DIR,
    DATA_ROOT,
    DB_DIR,
    DB_PATH,
    INDEX_DIR,
    NOTES_DIR,
    OCR_CACHE_DIR,
    SCREENSHOTS_CACHE_DIR,
    TEXT_BUFFERS_CACHE_DIR,
    ensure_data_directories,
    get_daily_cache_dirs,
    get_note_path,
)

__all__ = [
    # Directory paths
    "DATA_ROOT",
    "NOTES_DIR",
    "DB_DIR",
    "DB_PATH",
    "INDEX_DIR",
    "CACHE_DIR",
    "SCREENSHOTS_CACHE_DIR",
    "TEXT_BUFFERS_CACHE_DIR",
    "OCR_CACHE_DIR",
    # Functions
    "ensure_data_directories",
    "get_daily_cache_dirs",
    "get_note_path",
]
