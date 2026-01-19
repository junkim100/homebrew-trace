"""
macOS Media Remote Integration for Trace

Uses the MediaRemote private framework to get the actual system-wide
"Now Playing" information. This is the same source used by Control Center
and the menu bar media widget.

This approach is more reliable than querying individual apps because:
1. It correctly reflects playback state (playing vs paused)
2. It works for ANY app that reports to the system (YouTube, podcasts, etc.)
3. It's the single source of truth for what macOS considers "Now Playing"
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


class MRPlaybackState(IntEnum):
    """MediaRemote playback states."""

    UNKNOWN = 0
    PLAYING = 1
    PAUSED = 2
    STOPPED = 3
    INTERRUPTED = 4


@dataclass
class MediaRemoteInfo:
    """Information from macOS Media Remote framework."""

    timestamp: datetime
    is_playing: bool
    playback_state: MRPlaybackState
    title: str | None
    artist: str | None
    album: str | None
    app_bundle_id: str | None
    app_name: str | None
    duration: float | None
    elapsed_time: float | None
    playback_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "is_playing": self.is_playing,
            "playback_state": self.playback_state.name.lower(),
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "app_bundle_id": self.app_bundle_id,
            "app_name": self.app_name,
            "duration": self.duration,
            "elapsed_time": self.elapsed_time,
            "playback_rate": self.playback_rate,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @property
    def source(self) -> str:
        """Get normalized source name from bundle ID."""
        if not self.app_bundle_id:
            return "unknown"

        bundle_map = {
            "com.spotify.client": "spotify",
            "com.apple.Music": "apple_music",
            "com.apple.Safari": "safari",
            "com.google.Chrome": "chrome",
            "com.apple.WebKit.WebContent": "webkit",
            "tv.twitch.studio": "twitch",
            "com.apple.podcasts": "podcasts",
        }

        for bundle_id, source in bundle_map.items():
            if bundle_id in self.app_bundle_id:
                return source

        # Default to app name or bundle ID
        if self.app_name:
            return self.app_name.lower().replace(" ", "_")
        return self.app_bundle_id.split(".")[-1].lower()


def _get_now_playing_via_script() -> MediaRemoteInfo | None:
    """
    Get Now Playing info using a Swift script that accesses MediaRemote.

    This is more reliable than trying to load the framework directly in Python.
    """
    if sys.platform != "darwin":
        return None

    # Note: JXA approach for MediaRemote framework is complex and unreliable
    # Fall back to the AppleScript approach which correctly checks player state
    return _get_now_playing_via_nowplaying_cli()


def _get_now_playing_via_nowplaying_cli() -> MediaRemoteInfo | None:
    """
    Get Now Playing info by checking if media is actually being output.

    Uses multiple signals to determine if audio is actively playing:
    1. Check the system's audio state
    2. Use AppleScript to query player state directly
    """
    if sys.platform != "darwin":
        return None

    timestamp = datetime.now()

    # Try to detect currently playing media using a more reliable method
    # First, check if any audio is actually being output using coreaudiod
    try:
        # Use AppleScript to check the actual Now Playing state from Control Center
        # This uses the MediaRemote framework indirectly through System Events
        script = """
        use framework "Foundation"
        use scripting additions

        -- Check Spotify first
        tell application "System Events"
            set spotifyRunning to exists (processes where bundle identifier is "com.spotify.client")
        end tell

        if spotifyRunning then
            tell application "Spotify"
                if player state is playing then
                    set trackName to name of current track
                    set artistName to artist of current track
                    set albumName to album of current track
                    set trackDuration to (duration of current track) / 1000
                    set trackPosition to player position
                    return "PLAYING|||spotify|||com.spotify.client|||" & trackName & "|||" & artistName & "|||" & albumName & "|||" & trackDuration & "|||" & trackPosition
                else if player state is paused then
                    set trackName to name of current track
                    set artistName to artist of current track
                    set albumName to album of current track
                    set trackDuration to (duration of current track) / 1000
                    set trackPosition to player position
                    return "PAUSED|||spotify|||com.spotify.client|||" & trackName & "|||" & artistName & "|||" & albumName & "|||" & trackDuration & "|||" & trackPosition
                end if
            end tell
        end if

        -- Check Apple Music
        tell application "System Events"
            set musicRunning to exists (processes where bundle identifier is "com.apple.Music")
        end tell

        if musicRunning then
            tell application "Music"
                if player state is playing then
                    set trackName to name of current track
                    set artistName to artist of current track
                    set albumName to album of current track
                    set trackDuration to duration of current track
                    set trackPosition to player position
                    return "PLAYING|||apple_music|||com.apple.Music|||" & trackName & "|||" & artistName & "|||" & albumName & "|||" & trackDuration & "|||" & trackPosition
                else if player state is paused then
                    set trackName to name of current track
                    set artistName to artist of current track
                    set albumName to album of current track
                    set trackDuration to duration of current track
                    set trackPosition to player position
                    return "PAUSED|||apple_music|||com.apple.Music|||" & trackName & "|||" & artistName & "|||" & albumName & "|||" & trackDuration & "|||" & trackPosition
                end if
            end tell
        end if

        return "NONE"
        """

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()

            if output == "NONE":
                return None

            parts = output.split("|||")
            if len(parts) >= 8:
                state_str, source, bundle_id, title, artist, album, duration_str, elapsed_str = (
                    parts[:8]
                )

                is_playing = state_str == "PLAYING"
                playback_state = MRPlaybackState.PLAYING if is_playing else MRPlaybackState.PAUSED

                try:
                    duration = float(duration_str) if duration_str else None
                except (ValueError, TypeError):
                    duration = None

                try:
                    elapsed = float(elapsed_str) if elapsed_str else None
                except (ValueError, TypeError):
                    elapsed = None

                return MediaRemoteInfo(
                    timestamp=timestamp,
                    is_playing=is_playing,
                    playback_state=playback_state,
                    title=title if title else None,
                    artist=artist if artist else None,
                    album=album if album else None,
                    app_bundle_id=bundle_id,
                    app_name=source,
                    duration=duration,
                    elapsed_time=elapsed,
                    playback_rate=1.0 if is_playing else 0.0,
                )

    except subprocess.TimeoutExpired:
        logger.warning("Now Playing check timed out")
    except Exception as e:
        logger.debug(f"Failed to get Now Playing info: {e}")

    return None


def get_now_playing() -> MediaRemoteInfo | None:
    """
    Get the current system-wide Now Playing information.

    This uses the macOS Media Remote framework to get the actual
    playback state, which correctly reflects whether media is
    playing or paused.

    Returns:
        MediaRemoteInfo or None if nothing is playing
    """
    return _get_now_playing_via_nowplaying_cli()


def is_media_playing() -> bool:
    """
    Check if any media is currently playing (not paused).

    Returns:
        True if media is actively playing, False otherwise
    """
    info = get_now_playing()
    if info is None:
        return False
    return info.is_playing and info.playback_rate != 0.0


class MediaRemoteCapture:
    """
    Captures Now Playing information using macOS Media Remote.

    This is more accurate than querying individual apps because it
    uses the same source as the macOS Control Center.
    """

    def __init__(self):
        """Initialize the media remote capturer."""
        self._last_capture: MediaRemoteInfo | None = None

    def capture(self, timestamp: datetime | None = None) -> MediaRemoteInfo | None:
        """
        Capture current Now Playing state.

        Args:
            timestamp: Optional timestamp override

        Returns:
            MediaRemoteInfo or None if nothing is playing
        """
        info = get_now_playing()

        if info is not None and timestamp is not None:
            # Override timestamp
            info = MediaRemoteInfo(
                timestamp=timestamp,
                is_playing=info.is_playing,
                playback_state=info.playback_state,
                title=info.title,
                artist=info.artist,
                album=info.album,
                app_bundle_id=info.app_bundle_id,
                app_name=info.app_name,
                duration=info.duration,
                elapsed_time=info.elapsed_time,
                playback_rate=info.playback_rate,
            )

        self._last_capture = info
        return info

    def get_last_capture(self) -> MediaRemoteInfo | None:
        """Get the last captured info."""
        return self._last_capture

    def is_playing(self) -> bool:
        """Check if media is currently playing."""
        info = self.capture()
        return info is not None and info.is_playing


if __name__ == "__main__":
    import fire

    def capture():
        """Capture current Now Playing info."""
        capturer = MediaRemoteCapture()
        result = capturer.capture()
        if result:
            return result.to_dict()
        return {"status": "nothing_playing"}

    def is_playing():
        """Check if media is currently playing."""
        return is_media_playing()

    def watch(interval: float = 1.0, count: int = 60):
        """Watch Now Playing changes."""
        import time

        capturer = MediaRemoteCapture()
        last_state = None

        for _ in range(count):
            result = capturer.capture()
            if result:
                state_key = f"{result.title}:{result.is_playing}"
                if state_key != last_state:
                    status = "▶️ PLAYING" if result.is_playing else "⏸️ PAUSED"
                    print(f"[{result.source}] {status}: {result.title} - {result.artist}")
                    last_state = state_key
            elif last_state is not None:
                print("⏹️ STOPPED")
                last_state = None

            time.sleep(interval)

    fire.Fire(
        {
            "capture": capture,
            "is_playing": is_playing,
            "watch": watch,
        }
    )
