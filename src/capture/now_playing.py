"""
Now Playing Capture for Trace

Captures currently playing media information from:
- Spotify
- Apple Music (Music.app)

Uses AppleScript to communicate with the media applications.

P3-05: Now playing capture (Spotify)
P3-06: Now playing capture (Apple Music)
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class PlayerState(str, Enum):
    """Playback state of a media player."""

    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass
class NowPlaying:
    """Information about currently playing media."""

    timestamp: datetime
    source: str  # "spotify", "apple_music"
    state: PlayerState
    track: str | None
    artist: str | None
    album: str | None
    duration_seconds: float | None = None
    position_seconds: float | None = None
    artwork_url: str | None = None
    track_id: str | None = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(
            {
                "timestamp": self.timestamp.isoformat(),
                "source": self.source,
                "state": self.state.value,
                "track": self.track,
                "artist": self.artist,
                "album": self.album,
                "duration_seconds": self.duration_seconds,
                "position_seconds": self.position_seconds,
                "artwork_url": self.artwork_url,
                "track_id": self.track_id,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> "NowPlaying":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data["source"],
            state=PlayerState(data["state"]),
            track=data.get("track"),
            artist=data.get("artist"),
            album=data.get("album"),
            duration_seconds=data.get("duration_seconds"),
            position_seconds=data.get("position_seconds"),
            artwork_url=data.get("artwork_url"),
            track_id=data.get("track_id"),
        )


def _run_applescript(script: str) -> tuple[bool, str]:
    """Run an AppleScript and return (success, output)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning("AppleScript timed out")
        return False, ""
    except Exception as e:
        logger.error(f"Failed to run AppleScript: {e}")
        return False, ""


def _check_app_running(bundle_id: str) -> bool:
    """Check if an application is running."""
    script = f'''
    tell application "System Events"
        set appRunning to exists (processes where bundle identifier is "{bundle_id}")
        return appRunning
    end tell
    '''
    success, output = _run_applescript(script)
    return success and output.lower() == "true"


def capture_spotify(timestamp: datetime | None = None) -> NowPlaying | None:
    """
    Capture currently playing information from Spotify.

    Args:
        timestamp: Timestamp for the capture (defaults to now)

    Returns:
        NowPlaying information or None if Spotify is not playing
    """
    if sys.platform != "darwin":
        return None

    if timestamp is None:
        timestamp = datetime.now()

    # Check if Spotify is running
    if not _check_app_running("com.spotify.client"):
        return None

    # Get player state
    script = """
    tell application "Spotify"
        if player state is playing then
            return "playing"
        else if player state is paused then
            return "paused"
        else
            return "stopped"
        end if
    end tell
    """
    success, state_str = _run_applescript(script)
    if not success:
        return None

    try:
        state = PlayerState(state_str)
    except ValueError:
        state = PlayerState.UNKNOWN

    if state == PlayerState.STOPPED:
        return NowPlaying(
            timestamp=timestamp,
            source="spotify",
            state=state,
            track=None,
            artist=None,
            album=None,
        )

    # Get track information
    script = """
    tell application "Spotify"
        set trackName to name of current track
        set artistName to artist of current track
        set albumName to album of current track
        set trackDuration to (duration of current track) / 1000
        set trackPosition to player position
        set trackId to id of current track
        set artworkUrl to artwork url of current track
        return trackName & "|||" & artistName & "|||" & albumName & "|||" & trackDuration & "|||" & trackPosition & "|||" & trackId & "|||" & artworkUrl
    end tell
    """
    success, output = _run_applescript(script)

    if not success or not output:
        return NowPlaying(
            timestamp=timestamp,
            source="spotify",
            state=state,
            track=None,
            artist=None,
            album=None,
        )

    parts = output.split("|||")
    if len(parts) >= 7:
        track, artist, album, duration, position, track_id, artwork = parts[:7]
        return NowPlaying(
            timestamp=timestamp,
            source="spotify",
            state=state,
            track=track if track else None,
            artist=artist if artist else None,
            album=album if album else None,
            duration_seconds=float(duration) if duration else None,
            position_seconds=float(position) if position else None,
            track_id=track_id if track_id else None,
            artwork_url=artwork if artwork else None,
        )

    return NowPlaying(
        timestamp=timestamp,
        source="spotify",
        state=state,
        track=None,
        artist=None,
        album=None,
    )


def capture_apple_music(timestamp: datetime | None = None) -> NowPlaying | None:
    """
    Capture currently playing information from Apple Music (Music.app).

    Args:
        timestamp: Timestamp for the capture (defaults to now)

    Returns:
        NowPlaying information or None if Music is not playing
    """
    if sys.platform != "darwin":
        return None

    if timestamp is None:
        timestamp = datetime.now()

    # Check if Music is running
    if not _check_app_running("com.apple.Music"):
        return None

    # Get player state
    script = """
    tell application "Music"
        if player state is playing then
            return "playing"
        else if player state is paused then
            return "paused"
        else
            return "stopped"
        end if
    end tell
    """
    success, state_str = _run_applescript(script)
    if not success:
        return None

    try:
        state = PlayerState(state_str)
    except ValueError:
        state = PlayerState.UNKNOWN

    if state == PlayerState.STOPPED:
        return NowPlaying(
            timestamp=timestamp,
            source="apple_music",
            state=state,
            track=None,
            artist=None,
            album=None,
        )

    # Get track information
    script = """
    tell application "Music"
        set trackName to name of current track
        set artistName to artist of current track
        set albumName to album of current track
        set trackDuration to duration of current track
        set trackPosition to player position
        set trackId to id of current track
        return trackName & "|||" & artistName & "|||" & albumName & "|||" & trackDuration & "|||" & trackPosition & "|||" & trackId
    end tell
    """
    success, output = _run_applescript(script)

    if not success or not output:
        return NowPlaying(
            timestamp=timestamp,
            source="apple_music",
            state=state,
            track=None,
            artist=None,
            album=None,
        )

    parts = output.split("|||")
    if len(parts) >= 6:
        track, artist, album, duration, position, track_id = parts[:6]
        return NowPlaying(
            timestamp=timestamp,
            source="apple_music",
            state=state,
            track=track if track else None,
            artist=artist if artist else None,
            album=album if album else None,
            duration_seconds=float(duration) if duration else None,
            position_seconds=float(position) if position else None,
            track_id=str(track_id) if track_id else None,
            artwork_url=None,  # Apple Music doesn't expose artwork URL via AppleScript
        )

    return NowPlaying(
        timestamp=timestamp,
        source="apple_music",
        state=state,
        track=None,
        artist=None,
        album=None,
    )


class NowPlayingCapture:
    """
    Captures currently playing media from all supported sources.

    Prioritizes sources based on playback state (playing > paused > stopped).
    Only returns media that is ACTIVELY PLAYING - paused media is not returned
    to prevent false positives in activity tracking.
    """

    def __init__(self, include_paused: bool = False):
        """
        Initialize the now playing capturer.

        Args:
            include_paused: If True, also return paused media. Default is False
                           to prevent tracking paused media as "being listened to".
        """
        self._last_capture: NowPlaying | None = None
        self._include_paused = include_paused

    def capture(self, timestamp: datetime | None = None) -> NowPlaying | None:
        """
        Capture currently playing media from any active source.

        Checks Spotify and Apple Music, returning the one that is actively
        playing. By default, paused media is NOT returned to prevent false
        positives in activity tracking.

        Args:
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            NowPlaying information or None if no media is actively playing
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Try all sources
        sources = [
            ("spotify", capture_spotify),
            ("apple_music", capture_apple_music),
        ]

        candidates = []
        for name, capture_func in sources:
            try:
                result = capture_func(timestamp)
                if result:
                    # Only include if actually playing, unless include_paused is True
                    if result.state == PlayerState.PLAYING:
                        candidates.append(result)
                    elif self._include_paused and result.state == PlayerState.PAUSED:
                        candidates.append(result)
                    # Skip STOPPED and UNKNOWN states
            except Exception as e:
                logger.debug(f"Failed to capture from {name}: {e}")

        if not candidates:
            self._last_capture = None
            return None

        # Prioritize: playing > paused
        priority = {
            PlayerState.PLAYING: 0,
            PlayerState.PAUSED: 1,
        }

        candidates.sort(key=lambda x: priority.get(x.state, 99))
        self._last_capture = candidates[0]
        return self._last_capture

    def capture_all_states(self, timestamp: datetime | None = None) -> NowPlaying | None:
        """
        Capture media from any state (playing, paused, stopped).

        This is the original behavior that captures any media state.
        Use this when you need to know about paused media too.

        Args:
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            NowPlaying information or None if no media apps have content
        """
        if timestamp is None:
            timestamp = datetime.now()

        sources = [
            ("spotify", capture_spotify),
            ("apple_music", capture_apple_music),
        ]

        candidates = []
        for name, capture_func in sources:
            try:
                result = capture_func(timestamp)
                if result:
                    candidates.append(result)
            except Exception as e:
                logger.debug(f"Failed to capture from {name}: {e}")

        if not candidates:
            return None

        # Prioritize: playing > paused > stopped
        priority = {
            PlayerState.PLAYING: 0,
            PlayerState.PAUSED: 1,
            PlayerState.STOPPED: 2,
            PlayerState.UNKNOWN: 3,
        }

        candidates.sort(key=lambda x: priority.get(x.state, 99))
        return candidates[0]

    def is_playing(self) -> bool:
        """
        Check if any media is currently playing (not paused).

        Returns:
            True if media is actively playing, False otherwise
        """
        result = self.capture()
        return result is not None and result.state == PlayerState.PLAYING

    def get_last_capture(self) -> NowPlaying | None:
        """Get the last captured now playing information."""
        return self._last_capture


if __name__ == "__main__":
    import fire

    def spotify():
        """Capture Spotify now playing (any state)."""
        result = capture_spotify()
        if result:
            return json.loads(result.to_json())
        return None

    def apple_music():
        """Capture Apple Music now playing (any state)."""
        result = capture_apple_music()
        if result:
            return json.loads(result.to_json())
        return None

    def capture(include_paused: bool = False):
        """
        Capture from any active source.

        Args:
            include_paused: If True, also return paused media
        """
        capturer = NowPlayingCapture(include_paused=include_paused)
        result = capturer.capture()
        if result:
            return json.loads(result.to_json())
        return {"status": "nothing_playing", "note": "No media is actively playing"}

    def capture_all():
        """Capture from any source including paused/stopped."""
        capturer = NowPlayingCapture()
        result = capturer.capture_all_states()
        if result:
            return json.loads(result.to_json())
        return None

    def is_playing():
        """Check if any media is currently playing (not paused)."""
        capturer = NowPlayingCapture()
        return capturer.is_playing()

    def watch(interval: float = 1.0, count: int = 60, include_paused: bool = False):
        """
        Watch now playing changes with state indication.

        Args:
            interval: Check interval in seconds
            count: Number of checks to perform
            include_paused: Also show paused media
        """
        import time

        capturer = NowPlayingCapture(include_paused=include_paused)
        last_state = None

        for _ in range(count):
            result = capturer.capture()
            if result and result.track:
                state_key = f"{result.source}:{result.track}:{result.state.value}"
                if state_key != last_state:
                    icon = "▶️" if result.state == PlayerState.PLAYING else "⏸️"
                    print(
                        f"{icon} [{result.source}] {result.track} - {result.artist} ({result.state.value})"
                    )
                    last_state = state_key
            elif last_state is not None:
                print("⏹️ Nothing playing")
                last_state = None
            time.sleep(interval)

    fire.Fire(
        {
            "spotify": spotify,
            "apple_music": apple_music,
            "capture": capture,
            "capture_all": capture_all,
            "is_playing": is_playing,
            "watch": watch,
        }
    )
