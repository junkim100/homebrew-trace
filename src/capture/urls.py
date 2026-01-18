"""
Browser URL Capture for Trace

Captures the current URL and page title from web browsers:
- Safari (via AppleScript)
- Chrome (via AppleScript or Chrome DevTools Protocol)

P3-08: Safari URL capture
P3-09: Chrome URL capture
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BrowserURL:
    """Captured browser URL information."""

    timestamp: datetime
    browser: str  # "safari", "chrome", "firefox", etc.
    url: str | None
    title: str | None
    is_active: bool  # Whether this browser is the frontmost app

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(
            {
                "timestamp": self.timestamp.isoformat(),
                "browser": self.browser,
                "url": self.url,
                "title": self.title,
                "is_active": self.is_active,
            }
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


def _get_frontmost_app_bundle() -> str | None:
    """Get the bundle ID of the frontmost application."""
    if sys.platform != "darwin":
        return None

    try:
        from AppKit import NSWorkspace

        workspace = NSWorkspace.sharedWorkspace()
        frontmost_app = workspace.frontmostApplication()
        return frontmost_app.bundleIdentifier() if frontmost_app else None
    except Exception:
        return None


def capture_safari_url(timestamp: datetime | None = None) -> BrowserURL | None:
    """
    Capture the current URL and title from Safari.

    Uses AppleScript to get the URL and title of the front tab.

    Args:
        timestamp: Timestamp for the capture (defaults to now)

    Returns:
        BrowserURL with Safari information or None if Safari is not running
    """
    if sys.platform != "darwin":
        return None

    if timestamp is None:
        timestamp = datetime.now()

    # Check if Safari is running
    if not _check_app_running("com.apple.Safari"):
        return None

    # Get URL and title of the front tab
    script = """
    tell application "Safari"
        if (count of windows) > 0 then
            set theURL to URL of front document
            set theTitle to name of front document
            return theURL & "|||" & theTitle
        else
            return "|||"
        end if
    end tell
    """

    success, output = _run_applescript(script)

    if not success:
        return None

    parts = output.split("|||", 1)
    url = parts[0] if parts[0] else None
    title = parts[1] if len(parts) > 1 and parts[1] else None

    # Check if Safari is frontmost
    is_active = _get_frontmost_app_bundle() == "com.apple.Safari"

    return BrowserURL(
        timestamp=timestamp,
        browser="safari",
        url=url,
        title=title,
        is_active=is_active,
    )


def capture_chrome_url(timestamp: datetime | None = None) -> BrowserURL | None:
    """
    Capture the current URL and title from Google Chrome.

    Primarily uses AppleScript. Can also use Chrome DevTools Protocol
    if Chrome is started with --remote-debugging-port flag.

    Args:
        timestamp: Timestamp for the capture (defaults to now)

    Returns:
        BrowserURL with Chrome information or None if Chrome is not running
    """
    if sys.platform != "darwin":
        return None

    if timestamp is None:
        timestamp = datetime.now()

    # Check if Chrome is running
    if not _check_app_running("com.google.Chrome"):
        return None

    # Get URL and title of the active tab
    script = """
    tell application "Google Chrome"
        if (count of windows) > 0 then
            set theURL to URL of active tab of front window
            set theTitle to title of active tab of front window
            return theURL & "|||" & theTitle
        else
            return "|||"
        end if
    end tell
    """

    success, output = _run_applescript(script)

    if not success:
        # Try alternative approach - just get window name from System Events
        script = """
        tell application "System Events"
            tell process "Google Chrome"
                if (count of windows) > 0 then
                    return name of front window
                end if
            end tell
        end tell
        """
        success, window_name = _run_applescript(script)
        if success and window_name:
            return BrowserURL(
                timestamp=timestamp,
                browser="chrome",
                url=None,  # Can't get URL without automation permission
                title=window_name,
                is_active=_get_frontmost_app_bundle() == "com.google.Chrome",
            )
        return None

    parts = output.split("|||", 1)
    url = parts[0] if parts[0] else None
    title = parts[1] if len(parts) > 1 and parts[1] else None

    # Check if Chrome is frontmost
    is_active = _get_frontmost_app_bundle() == "com.google.Chrome"

    return BrowserURL(
        timestamp=timestamp,
        browser="chrome",
        url=url,
        title=title,
        is_active=is_active,
    )


def capture_firefox_url(timestamp: datetime | None = None) -> BrowserURL | None:
    """
    Capture the current URL and title from Firefox.

    Firefox has limited AppleScript support, so this mainly captures
    the window title which often includes the page title.

    Args:
        timestamp: Timestamp for the capture (defaults to now)

    Returns:
        BrowserURL with Firefox information or None
    """
    if sys.platform != "darwin":
        return None

    if timestamp is None:
        timestamp = datetime.now()

    # Check if Firefox is running
    if not _check_app_running("org.mozilla.firefox"):
        return None

    # Firefox doesn't support URL retrieval via AppleScript
    # Try to get the window title which usually contains the page title
    script = """
    tell application "System Events"
        tell process "Firefox"
            if (count of windows) > 0 then
                return name of front window
            end if
        end tell
    end tell
    """

    success, window_name = _run_applescript(script)

    if not success:
        return None

    # Firefox window titles are usually "Page Title — Mozilla Firefox"
    title = window_name
    if " — Mozilla Firefox" in title:
        title = title.replace(" — Mozilla Firefox", "")
    elif " - Mozilla Firefox" in title:
        title = title.replace(" - Mozilla Firefox", "")

    is_active = _get_frontmost_app_bundle() == "org.mozilla.firefox"

    return BrowserURL(
        timestamp=timestamp,
        browser="firefox",
        url=None,  # Firefox doesn't expose URL via AppleScript
        title=title if title else None,
        is_active=is_active,
    )


# Browser bundle IDs and their capture functions
BROWSER_CAPTURERS = {
    "com.apple.Safari": ("safari", capture_safari_url),
    "com.google.Chrome": ("chrome", capture_chrome_url),
    "org.mozilla.firefox": ("firefox", capture_firefox_url),
    "com.microsoft.Edge": ("edge", None),  # TODO: Similar to Chrome
    "com.brave.Browser": ("brave", None),  # TODO: Similar to Chrome
    "com.operasoftware.Opera": ("opera", None),  # TODO: Similar to Chrome
}


class URLCapture:
    """
    Captures browser URLs from the active browser.

    Automatically detects which browser is active and captures its URL.
    """

    def __init__(self):
        """Initialize the URL capturer."""
        self._last_capture: BrowserURL | None = None

    def capture(self, timestamp: datetime | None = None) -> BrowserURL | None:
        """
        Capture the URL from the active browser.

        Checks which browser (if any) is frontmost and captures its URL.

        Args:
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            BrowserURL information or None if no browser is active
        """
        if timestamp is None:
            timestamp = datetime.now()

        frontmost_bundle = _get_frontmost_app_bundle()

        if frontmost_bundle in BROWSER_CAPTURERS:
            _name, capture_func = BROWSER_CAPTURERS[frontmost_bundle]
            if capture_func:
                result = capture_func(timestamp)
                if result:
                    self._last_capture = result
                    return result

        return None

    def capture_all(self, timestamp: datetime | None = None) -> list[BrowserURL]:
        """
        Capture URLs from all running browsers.

        Args:
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            List of BrowserURL for all running browsers
        """
        if timestamp is None:
            timestamp = datetime.now()

        results = []

        for bundle_id, (_name, capture_func) in BROWSER_CAPTURERS.items():
            if capture_func and _check_app_running(bundle_id):
                try:
                    result = capture_func(timestamp)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug(f"Failed to capture from {bundle_id}: {e}")

        return results

    def get_active_browser_url(
        self, foreground_bundle_id: str | None, timestamp: datetime | None = None
    ) -> BrowserURL | None:
        """
        Capture URL if the foreground app is a browser.

        Args:
            foreground_bundle_id: Bundle ID of the current foreground app
            timestamp: Timestamp for the capture (defaults to now)

        Returns:
            BrowserURL if foreground is a browser, otherwise None
        """
        if foreground_bundle_id not in BROWSER_CAPTURERS:
            return None

        _name, capture_func = BROWSER_CAPTURERS[foreground_bundle_id]
        if capture_func:
            return capture_func(timestamp)

        return None

    def get_last_capture(self) -> BrowserURL | None:
        """Get the last captured browser URL."""
        return self._last_capture


if __name__ == "__main__":
    import fire

    def safari():
        """Capture Safari URL."""
        result = capture_safari_url()
        if result:
            return json.loads(result.to_json())
        return None

    def chrome():
        """Capture Chrome URL."""
        result = capture_chrome_url()
        if result:
            return json.loads(result.to_json())
        return None

    def firefox():
        """Capture Firefox URL."""
        result = capture_firefox_url()
        if result:
            return json.loads(result.to_json())
        return None

    def capture():
        """Capture from the active browser."""
        capturer = URLCapture()
        result = capturer.capture()
        if result:
            return json.loads(result.to_json())
        return {"message": "No browser is active"}

    def all_browsers():
        """Capture from all running browsers."""
        capturer = URLCapture()
        results = capturer.capture_all()
        return [json.loads(r.to_json()) for r in results]

    def watch(interval: float = 1.0, count: int = 30):
        """Watch browser URL changes."""
        import time

        capturer = URLCapture()
        last_url = None

        for _ in range(count):
            result = capturer.capture()
            if result and result.url:
                if result.url != last_url:
                    print(f"[{result.browser}] {result.url}")
                    print(f"  Title: {result.title}")
                    last_url = result.url
            time.sleep(interval)

    fire.Fire(
        {
            "safari": safari,
            "chrome": chrome,
            "firefox": firefox,
            "capture": capture,
            "all": all_browsers,
            "watch": watch,
        }
    )
