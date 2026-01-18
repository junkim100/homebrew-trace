"""
Multi-monitor Screenshot Capture for Trace

Captures screenshots from all connected monitors at configurable intervals.
Screenshots are downscaled to a maximum resolution of 1080p to save storage.

P3-01: Multi-monitor screenshot capture
"""

import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from src.core.paths import ensure_daily_cache_dirs

logger = logging.getLogger(__name__)

# Maximum resolution for saved screenshots (1080p)
MAX_HEIGHT = 1080
MAX_WIDTH = 1920


@dataclass
class MonitorInfo:
    """Information about a display monitor."""

    monitor_id: int
    x: int
    y: int
    width: int
    height: int
    is_main: bool = False


@dataclass
class CapturedScreenshot:
    """Result of a screenshot capture."""

    screenshot_id: str
    timestamp: datetime
    monitor_id: int
    path: Path
    width: int
    height: int
    original_width: int
    original_height: int


def _get_monitors_macos() -> list[MonitorInfo]:
    """Get information about all connected monitors on macOS."""
    if sys.platform != "darwin":
        return []

    try:
        from Quartz import (
            CGDisplayBounds,
            CGGetActiveDisplayList,
            CGMainDisplayID,
        )

        max_displays = 16
        error, active_displays, count = CGGetActiveDisplayList(max_displays, None, None)

        if error != 0:
            logger.error(f"CGGetActiveDisplayList returned error: {error}")
            return []

        if count == 0:
            logger.warning("No displays found")
            return []

        main_display_id = CGMainDisplayID()
        monitors = []

        for i in range(count):
            display_id = active_displays[i]
            bounds = CGDisplayBounds(display_id)

            monitors.append(
                MonitorInfo(
                    monitor_id=display_id,
                    x=int(bounds.origin.x),
                    y=int(bounds.origin.y),
                    width=int(bounds.size.width),
                    height=int(bounds.size.height),
                    is_main=(display_id == main_display_id),
                )
            )

        return monitors
    except ImportError:
        logger.error("Quartz framework not available")
        return []
    except Exception as e:
        logger.error(f"Failed to get monitor list: {e}")
        return []


def _capture_display_macos(display_id: int) -> Image.Image | None:
    """Capture a single display on macOS."""
    if sys.platform != "darwin":
        return None

    try:
        from Quartz import (
            CGDataProviderCopyData,
            CGDisplayCreateImage,
            CGImageGetBytesPerRow,
            CGImageGetDataProvider,
            CGImageGetHeight,
            CGImageGetWidth,
        )

        # Capture the display
        cg_image = CGDisplayCreateImage(display_id)
        if cg_image is None:
            logger.warning(f"Failed to capture display {display_id}")
            return None

        # Get image dimensions using functions
        width = CGImageGetWidth(cg_image)
        height = CGImageGetHeight(cg_image)
        bytes_per_row = CGImageGetBytesPerRow(cg_image)

        # Get raw pixel data
        provider = CGImageGetDataProvider(cg_image)
        data = CGDataProviderCopyData(provider)

        # Convert to PIL Image
        # CGImage uses BGRA format
        image = Image.frombytes("RGBA", (width, height), bytes(data), "raw", "BGRA", bytes_per_row)
        return image

    except ImportError:
        logger.error("Quartz framework not available")
        return None
    except Exception as e:
        logger.error(f"Failed to capture display {display_id}: {e}")
        return None


def _downscale_image(image: Image.Image) -> Image.Image:
    """
    Downscale an image to fit within MAX_WIDTH x MAX_HEIGHT while maintaining aspect ratio.

    Args:
        image: Original PIL Image

    Returns:
        Downscaled image (or original if already within limits)
    """
    width, height = image.size

    if width <= MAX_WIDTH and height <= MAX_HEIGHT:
        return image

    # Calculate scale factor to fit within max dimensions
    scale_w = MAX_WIDTH / width
    scale_h = MAX_HEIGHT / height
    scale = min(scale_w, scale_h)

    new_width = int(width * scale)
    new_height = int(height * scale)

    # Use LANCZOS resampling for high-quality downscaling
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


class MultiMonitorCapture:
    """
    Captures screenshots from all connected monitors.

    Screenshots are saved as JPEG files in the daily cache directory,
    downscaled to fit within 1080p resolution.
    """

    def __init__(self, jpeg_quality: int = 85):
        """
        Initialize the screenshot capturer.

        Args:
            jpeg_quality: JPEG compression quality (1-100)
        """
        self.jpeg_quality = jpeg_quality
        self._monitors: list[MonitorInfo] = []
        self._last_refresh = datetime.min

    def refresh_monitors(self) -> list[MonitorInfo]:
        """Refresh the list of connected monitors."""
        self._monitors = _get_monitors_macos()
        self._last_refresh = datetime.now()
        logger.debug(f"Refreshed monitor list: {len(self._monitors)} monitors")
        return self._monitors

    def get_monitors(self) -> list[MonitorInfo]:
        """Get the current list of monitors."""
        if not self._monitors:
            self.refresh_monitors()
        return self._monitors

    def capture_all(self, timestamp: datetime | None = None) -> list[CapturedScreenshot]:
        """
        Capture screenshots from all monitors.

        Args:
            timestamp: Timestamp to use for the captures (defaults to now)

        Returns:
            List of captured screenshots
        """
        if timestamp is None:
            timestamp = datetime.now()

        monitors = self.get_monitors()
        if not monitors:
            logger.warning("No monitors available for capture")
            return []

        # Ensure cache directory exists
        cache_dirs = ensure_daily_cache_dirs(timestamp)
        screenshots_dir = cache_dirs["screenshots"]

        results = []

        for monitor in monitors:
            try:
                screenshot = self._capture_monitor(monitor, timestamp, screenshots_dir)
                if screenshot:
                    results.append(screenshot)
            except Exception as e:
                logger.error(f"Failed to capture monitor {monitor.monitor_id}: {e}")

        return results

    def _capture_monitor(
        self, monitor: MonitorInfo, timestamp: datetime, output_dir: Path
    ) -> CapturedScreenshot | None:
        """Capture a single monitor and save to disk."""
        image = _capture_display_macos(monitor.monitor_id)
        if image is None:
            return None

        original_width, original_height = image.size

        # Downscale if necessary
        image = _downscale_image(image)
        final_width, final_height = image.size

        # Convert to RGB for JPEG (remove alpha channel)
        if image.mode == "RGBA":
            image = image.convert("RGB")

        # Generate unique ID and filename
        screenshot_id = str(uuid.uuid4())
        ts_str = timestamp.strftime("%H%M%S%f")[:-3]  # HHMMSS + milliseconds
        filename = f"{ts_str}_m{monitor.monitor_id}_{screenshot_id[:8]}.jpg"
        output_path = output_dir / filename

        # Save the image
        image.save(output_path, "JPEG", quality=self.jpeg_quality)

        logger.debug(f"Captured monitor {monitor.monitor_id}: {output_path}")

        return CapturedScreenshot(
            screenshot_id=screenshot_id,
            timestamp=timestamp,
            monitor_id=monitor.monitor_id,
            path=output_path,
            width=final_width,
            height=final_height,
            original_width=original_width,
            original_height=original_height,
        )


if __name__ == "__main__":
    import fire

    def list_monitors():
        """List all connected monitors."""
        capture = MultiMonitorCapture()
        monitors = capture.refresh_monitors()
        return [
            {
                "monitor_id": m.monitor_id,
                "x": m.x,
                "y": m.y,
                "width": m.width,
                "height": m.height,
                "is_main": m.is_main,
            }
            for m in monitors
        ]

    def capture():
        """Capture screenshots from all monitors."""
        capture_instance = MultiMonitorCapture()
        results = capture_instance.capture_all()
        return [
            {
                "screenshot_id": r.screenshot_id,
                "monitor_id": r.monitor_id,
                "path": str(r.path),
                "width": r.width,
                "height": r.height,
                "original_width": r.original_width,
                "original_height": r.original_height,
            }
            for r in results
        ]

    fire.Fire(
        {
            "monitors": list_monitors,
            "capture": capture,
        }
    )
