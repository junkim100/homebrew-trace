"""
Capture Daemon Module for Trace

This module contains all capture functionality:
- Multi-monitor screenshot capture
- Screenshot deduplication
- Foreground app/window metadata
- Event span tracking
- Now playing (Spotify, Apple Music)
- Location capture
- Browser URL capture (Safari, Chrome)
- Main daemon orchestrator
"""

from src.capture.daemon import CaptureDaemon
from src.capture.dedup import compute_perceptual_hash, is_duplicate
from src.capture.events import EventTracker
from src.capture.foreground import capture_foreground_app
from src.capture.location import LocationCapture
from src.capture.now_playing import NowPlayingCapture
from src.capture.screenshots import MultiMonitorCapture
from src.capture.urls import URLCapture

__all__ = [
    "CaptureDaemon",
    "MultiMonitorCapture",
    "compute_perceptual_hash",
    "is_duplicate",
    "capture_foreground_app",
    "EventTracker",
    "NowPlayingCapture",
    "LocationCapture",
    "URLCapture",
]
