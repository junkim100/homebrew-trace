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
    """

    def __init__(self):
        """Initialize the now playing capturer."""
        self._last_capture: NowPlaying | None = None

    def capture(self, timestamp: datetime | None = None) -> NowPlaying | None:
        """
        Capture currently playing media from any active source.

        Checks Spotify and Apple Music, returning the one that is actively
        playing (or paused if nothing is playing).

        Args:
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            NowPlaying information or None if no media is playing
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
        self._last_capture = candidates[0]
        return self._last_capture

    def get_last_capture(self) -> NowPlaying | None:
        """Get the last captured now playing information."""
        return self._last_capture


if __name__ == "__main__":
    import fire

    def spotify():
        """Capture Spotify now playing."""
        result = capture_spotify()
        if result:
            return json.loads(result.to_json())
        return None

    def apple_music():
        """Capture Apple Music now playing."""
        result = capture_apple_music()
        if result:
            return json.loads(result.to_json())
        return None

    def capture():
        """Capture from any active source."""
        capturer = NowPlayingCapture()
        result = capturer.capture()
        if result:
            return json.loads(result.to_json())
        return None

    def watch(interval: float = 2.0, count: int = 30):
        """Watch now playing changes."""
        import time

        capturer = NowPlayingCapture()
        last_track = None

        for _ in range(count):
            result = capturer.capture()
            if result and result.track:
                track_key = f"{result.source}:{result.track}"
                if track_key != last_track:
                    print(
                        f"[{result.source}] {result.track} - {result.artist} ({result.state.value})"
                    )
                    last_track = track_key
            time.sleep(interval)

    fire.Fire(
        {
            "spotify": spotify,
            "apple_music": apple_music,
            "capture": capture,
            "watch": watch,
        }
    )
