"""
Foreground App and Window Metadata Capture for Trace

Captures information about the currently active application and window:
- Bundle ID (e.g., com.apple.Safari)
- Application name (e.g., Safari)
- Window title
- Monitor ID where the focused window is displayed

P3-03: Foreground app/window metadata capture
"""

import logging
import sys
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ForegroundApp:
    """Information about the currently focused application."""

    timestamp: datetime
    bundle_id: str | None
    app_name: str | None
    window_title: str | None
    focused_monitor: int | None
    pid: int | None


def _get_frontmost_app_macos() -> tuple[str | None, str | None, int | None]:
    """
    Get the frontmost application on macOS.

    Returns:
        Tuple of (bundle_id, app_name, pid)
    """
    if sys.platform != "darwin":
        return None, None, None

    try:
        from AppKit import NSWorkspace

        workspace = NSWorkspace.sharedWorkspace()
        frontmost_app = workspace.frontmostApplication()

        if frontmost_app is None:
            return None, None, None

        bundle_id = frontmost_app.bundleIdentifier()
        app_name = frontmost_app.localizedName()
        pid = frontmost_app.processIdentifier()

        return bundle_id, app_name, pid

    except ImportError:
        logger.error("AppKit not available")
        return None, None, None
    except Exception as e:
        logger.error(f"Failed to get frontmost app: {e}")
        return None, None, None


def _get_focused_window_title_macos(pid: int | None) -> str | None:
    """
    Get the title of the focused window on macOS.

    Uses the Accessibility API to get the window title of the frontmost window
    for the given process.

    Args:
        pid: Process ID of the frontmost application

    Returns:
        Window title or None if not available
    """
    if sys.platform != "darwin":
        return None

    if pid is None:
        return None

    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )

        # Get all on-screen windows
        options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)

        if window_list is None:
            return None

        # Find the topmost window from the target process
        for window in window_list:
            window_pid = window.get("kCGWindowOwnerPID")
            if window_pid == pid:
                # Check if it's a regular window (layer 0 is normal windows)
                layer = window.get("kCGWindowLayer", -1)
                if layer == 0:
                    title = window.get("kCGWindowName", "")
                    return title if title else None

        return None

    except ImportError:
        logger.warning("Quartz framework not available for window title")
        return None
    except Exception as e:
        logger.error(f"Failed to get window title: {e}")
        return None


def _get_focused_window_title_accessibility(pid: int | None) -> str | None:
    """
    Get the focused window title using Accessibility API.

    This is a more reliable method but requires Accessibility permission.

    Args:
        pid: Process ID of the frontmost application

    Returns:
        Window title or None
    """
    if sys.platform != "darwin":
        return None

    if pid is None:
        return None

    try:
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication,
            kAXErrorSuccess,
        )

        # Create an accessibility element for the app
        app_element = AXUIElementCreateApplication(pid)

        # Get the focused window
        error_code, focused_window = AXUIElementCopyAttributeValue(
            app_element, "AXFocusedWindow", None
        )

        if error_code != kAXErrorSuccess or focused_window is None:
            # Try getting the main window instead
            error_code, focused_window = AXUIElementCopyAttributeValue(
                app_element, "AXMainWindow", None
            )
            if error_code != kAXErrorSuccess or focused_window is None:
                return None

        # Get the window title
        error_code, title = AXUIElementCopyAttributeValue(focused_window, "AXTitle", None)

        if error_code == kAXErrorSuccess and title:
            return str(title)

        return None

    except ImportError:
        logger.warning("ApplicationServices not available")
        return None
    except Exception as e:
        logger.debug(f"Accessibility API failed: {e}")
        return None


def _get_focused_monitor_macos(pid: int | None) -> int | None:
    """
    Get the monitor ID where the focused window is displayed.

    Args:
        pid: Process ID of the frontmost application

    Returns:
        Monitor (display) ID or None
    """
    if sys.platform != "darwin":
        return None

    if pid is None:
        return None

    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )

        # Get all on-screen windows
        options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)

        if window_list is None:
            return None

        # Find the frontmost window from the target process
        for window in window_list:
            window_pid = window.get("kCGWindowOwnerPID")
            layer = window.get("kCGWindowLayer", -1)

            if window_pid == pid and layer == 0:
                # Get the window bounds
                bounds = window.get("kCGWindowBounds")
                if bounds:
                    # Get the center point of the window
                    center_x = bounds.get("X", 0) + bounds.get("Width", 0) / 2
                    center_y = bounds.get("Y", 0) + bounds.get("Height", 0) / 2

                    # Find which display contains this point
                    return _get_display_at_point(center_x, center_y)

        return None

    except ImportError:
        return None
    except Exception as e:
        logger.error(f"Failed to get focused monitor: {e}")
        return None


def _get_display_at_point(x: float, y: float) -> int | None:
    """Get the display ID that contains the given point."""
    try:
        from Quartz import CGDisplayBounds, CGGetActiveDisplayList

        max_displays = 16
        active_displays, count = CGGetActiveDisplayList(max_displays, None, None)

        if count == 0:
            return None

        for i in range(count):
            display_id = active_displays[i]
            bounds = CGDisplayBounds(display_id)

            # Check if point is within this display's bounds
            if (
                bounds.origin.x <= x < bounds.origin.x + bounds.size.width
                and bounds.origin.y <= y < bounds.origin.y + bounds.size.height
            ):
                return display_id

        return None

    except Exception:
        return None


def capture_foreground_app(timestamp: datetime | None = None) -> ForegroundApp:
    """
    Capture information about the currently focused application and window.

    Args:
        timestamp: Timestamp for the capture (defaults to now)

    Returns:
        ForegroundApp with captured metadata
    """
    if timestamp is None:
        timestamp = datetime.now()

    bundle_id, app_name, pid = _get_frontmost_app_macos()

    # Try accessibility API first (more reliable), fall back to CGWindow
    window_title = _get_focused_window_title_accessibility(pid)
    if window_title is None:
        window_title = _get_focused_window_title_macos(pid)

    focused_monitor = _get_focused_monitor_macos(pid)

    return ForegroundApp(
        timestamp=timestamp,
        bundle_id=bundle_id,
        app_name=app_name,
        window_title=window_title,
        focused_monitor=focused_monitor,
        pid=pid,
    )


if __name__ == "__main__":
    import fire

    def capture():
        """Capture current foreground app information."""
        result = capture_foreground_app()
        return {
            "timestamp": result.timestamp.isoformat(),
            "bundle_id": result.bundle_id,
            "app_name": result.app_name,
            "window_title": result.window_title,
            "focused_monitor": result.focused_monitor,
            "pid": result.pid,
        }

    def watch(interval: float = 1.0, count: int = 10):
        """Watch foreground app changes."""
        import time

        results = []
        for _ in range(count):
            result = capture_foreground_app()
            entry = {
                "time": result.timestamp.strftime("%H:%M:%S"),
                "app": result.app_name,
                "window": result.window_title[:50] if result.window_title else None,
            }
            results.append(entry)
            print(entry)
            time.sleep(interval)
        return results

    fire.Fire(
        {
            "capture": capture,
            "watch": watch,
        }
    )
