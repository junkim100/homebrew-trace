"""
macOS Permission Management for Trace

This module provides functionality to check and manage macOS permissions required
by Trace for screen recording, accessibility, and location services.

Permissions required:
- Screen Recording: Required for capturing screenshots of all displays
- Accessibility: Required for getting foreground app/window information
- Location Services: Required for location capture feature

Note: macOS requires app restart after granting Screen Recording permission.
"""

import logging
import subprocess
import sys
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    """macOS permissions required by Trace."""

    SCREEN_RECORDING = "screen_recording"
    ACCESSIBILITY = "accessibility"
    LOCATION = "location"


class PermissionStatus(str, Enum):
    """Status of a permission."""

    GRANTED = "granted"
    DENIED = "denied"
    NOT_DETERMINED = "not_determined"
    RESTRICTED = "restricted"  # System policy prevents granting


class PermissionState(BaseModel):
    """State of a single permission."""

    permission: Permission = Field(..., description="The permission type")
    status: PermissionStatus = Field(..., description="Current status")
    required: bool = Field(default=True, description="Whether this permission is required")
    can_request: bool = Field(default=True, description="Whether the permission can be requested")


class AllPermissionsState(BaseModel):
    """State of all permissions."""

    screen_recording: PermissionState
    accessibility: PermissionState
    location: PermissionState
    all_granted: bool = Field(..., description="Whether all required permissions are granted")
    requires_restart: bool = Field(
        default=False,
        description="Whether app restart is needed after granting permissions",
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


def _check_screen_recording_permission() -> PermissionStatus:
    """
    Check Screen Recording permission status.

    Uses CGWindowListCopyWindowInfo to determine if screen recording is allowed.
    This is the only reliable way to check screen recording permission.
    """
    if sys.platform != "darwin":
        return PermissionStatus.GRANTED

    try:
        # Import here to avoid issues on non-macOS platforms
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )

        # Try to get window list - this requires screen recording permission
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)

        if window_list is None:
            return PermissionStatus.DENIED

        # Check if we can see window names from other apps
        # Without permission, we only see our own app's windows
        for window in window_list:
            owner_name = window.get("kCGWindowOwnerName", "")
            # If we can see window info from any app, we have permission
            if owner_name and owner_name != "Python":
                return PermissionStatus.GRANTED

        # If we only see our own windows or none, permission may not be granted
        # But this could also mean no other windows are visible
        # A more robust check is to attempt a screenshot
        return _verify_screenshot_capability()

    except ImportError:
        logger.warning("Quartz not available, assuming screen recording permission granted")
        return PermissionStatus.NOT_DETERMINED
    except Exception as e:
        logger.error(f"Error checking screen recording permission: {e}")
        return PermissionStatus.NOT_DETERMINED


def _verify_screenshot_capability() -> PermissionStatus:
    """Verify we can actually capture screenshots."""
    try:
        from Quartz import CGDisplayCreateImage, CGMainDisplayID

        display_id = CGMainDisplayID()
        image = CGDisplayCreateImage(display_id)

        if image is None:
            return PermissionStatus.DENIED
        return PermissionStatus.GRANTED
    except Exception as e:
        logger.error(f"Screenshot capability check failed: {e}")
        return PermissionStatus.NOT_DETERMINED


def _check_accessibility_permission() -> PermissionStatus:
    """
    Check Accessibility permission status.

    Uses AXIsProcessTrusted to determine if accessibility is enabled.
    """
    if sys.platform != "darwin":
        return PermissionStatus.GRANTED

    try:
        from ApplicationServices import AXIsProcessTrusted

        if AXIsProcessTrusted():
            return PermissionStatus.GRANTED
        return PermissionStatus.DENIED
    except ImportError:
        logger.warning(
            "ApplicationServices not available, assuming accessibility permission granted"
        )
        return PermissionStatus.NOT_DETERMINED
    except Exception as e:
        logger.error(f"Error checking accessibility permission: {e}")
        return PermissionStatus.NOT_DETERMINED


def _check_location_permission() -> PermissionStatus:
    """
    Check Location Services permission status.

    Uses CoreLocation to check authorization status.
    """
    if sys.platform != "darwin":
        return PermissionStatus.GRANTED

    try:
        from CoreLocation import CLLocationManager

        # Check if location services are enabled globally
        if not CLLocationManager.locationServicesEnabled():
            return PermissionStatus.RESTRICTED

        # Check our app's authorization status
        status = CLLocationManager.authorizationStatus()

        # Status values:
        # 0 = kCLAuthorizationStatusNotDetermined
        # 1 = kCLAuthorizationStatusRestricted
        # 2 = kCLAuthorizationStatusDenied
        # 3 = kCLAuthorizationStatusAuthorizedAlways
        # 4 = kCLAuthorizationStatusAuthorizedWhenInUse

        status_map = {
            0: PermissionStatus.NOT_DETERMINED,
            1: PermissionStatus.RESTRICTED,
            2: PermissionStatus.DENIED,
            3: PermissionStatus.GRANTED,
            4: PermissionStatus.GRANTED,  # WhenInUse is sufficient for our needs
        }

        return status_map.get(status, PermissionStatus.NOT_DETERMINED)

    except ImportError:
        logger.warning("CoreLocation not available, assuming location permission granted")
        return PermissionStatus.NOT_DETERMINED
    except Exception as e:
        logger.error(f"Error checking location permission: {e}")
        return PermissionStatus.NOT_DETERMINED


def check_permission(permission: Permission) -> PermissionState:
    """
    Check the status of a specific permission.

    Args:
        permission: The permission to check

    Returns:
        PermissionState with current status
    """
    checkers = {
        Permission.SCREEN_RECORDING: _check_screen_recording_permission,
        Permission.ACCESSIBILITY: _check_accessibility_permission,
        Permission.LOCATION: _check_location_permission,
    }

    checker = checkers.get(permission)
    if checker is None:
        raise ValueError(f"Unknown permission: {permission}")

    status = checker()

    return PermissionState(
        permission=permission,
        status=status,
        required=permission != Permission.LOCATION,  # Location is optional
        can_request=status in (PermissionStatus.NOT_DETERMINED, PermissionStatus.DENIED),
    )


def check_all_permissions() -> AllPermissionsState:
    """
    Check the status of all required permissions.

    Returns:
        AllPermissionsState with status of all permissions
    """
    screen_recording = check_permission(Permission.SCREEN_RECORDING)
    accessibility = check_permission(Permission.ACCESSIBILITY)
    location = check_permission(Permission.LOCATION)

    all_required_granted = (
        screen_recording.status == PermissionStatus.GRANTED
        and accessibility.status == PermissionStatus.GRANTED
    )

    # Screen recording permission requires app restart after granting
    requires_restart = screen_recording.status == PermissionStatus.DENIED

    return AllPermissionsState(
        screen_recording=screen_recording,
        accessibility=accessibility,
        location=location,
        all_granted=all_required_granted,
        requires_restart=requires_restart,
    )


def get_permission_instructions(permission: Permission) -> dict[str, Any]:
    """
    Get user-friendly instructions for granting a permission.

    Args:
        permission: The permission to get instructions for

    Returns:
        Dictionary with title, description, and steps
    """
    instructions = {
        Permission.SCREEN_RECORDING: {
            "title": "Screen Recording",
            "description": "Trace needs screen recording permission to capture screenshots of your activity.",
            "steps": [
                "Open System Settings",
                "Go to Privacy & Security > Screen Recording",
                "Find Trace in the list and enable it",
                "If Trace is not listed, click the + button and add it",
                "Restart Trace after enabling the permission",
            ],
            "system_preferences_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            "requires_restart": True,
        },
        Permission.ACCESSIBILITY: {
            "title": "Accessibility",
            "description": "Trace needs accessibility permission to detect which app and window you're using.",
            "steps": [
                "Open System Settings",
                "Go to Privacy & Security > Accessibility",
                "Find Trace in the list and enable it",
                "If Trace is not listed, click the + button and add it",
            ],
            "system_preferences_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "requires_restart": False,
        },
        Permission.LOCATION: {
            "title": "Location Services",
            "description": "Trace can optionally capture your location to add context to your notes.",
            "steps": [
                "Open System Settings",
                "Go to Privacy & Security > Location Services",
                "Find Trace in the list and enable it",
                "If Trace is not listed, click the + button and add it",
            ],
            "system_preferences_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices",
            "requires_restart": False,
        },
    }

    return instructions.get(permission, {})


def open_system_preferences(permission: Permission) -> bool:
    """
    Open System Preferences/Settings to the relevant permission pane.

    Args:
        permission: The permission pane to open

    Returns:
        True if successfully opened, False otherwise
    """
    if sys.platform != "darwin":
        logger.warning("System preferences can only be opened on macOS")
        return False

    instructions = get_permission_instructions(permission)
    url = instructions.get("system_preferences_url", "")

    if not url:
        logger.error(f"No system preferences URL for permission: {permission}")
        return False

    try:
        subprocess.run(["open", url], check=True, timeout=5)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to open system preferences: {e}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Timed out opening system preferences")
        return False


def request_accessibility_permission() -> bool:
    """
    Trigger the system accessibility permission prompt.

    Returns:
        True if the prompt was triggered successfully
    """
    if sys.platform != "darwin":
        return False

    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        from Foundation import NSDictionary

        # This will show the system prompt if permission is not already granted
        options = NSDictionary.dictionaryWithObject_forKey_(True, "AXTrustedCheckOptionPrompt")
        AXIsProcessTrustedWithOptions(options)
        return True
    except ImportError:
        logger.warning("ApplicationServices not available")
        return False
    except Exception as e:
        logger.error(f"Failed to request accessibility permission: {e}")
        return False


def request_location_permission() -> bool:
    """
    Trigger the system location permission prompt.

    Returns:
        True if the prompt was triggered successfully
    """
    if sys.platform != "darwin":
        return False

    try:
        from CoreLocation import CLLocationManager

        manager = CLLocationManager.alloc().init()
        manager.requestWhenInUseAuthorization()
        return True
    except ImportError:
        logger.warning("CoreLocation not available")
        return False
    except Exception as e:
        logger.error(f"Failed to request location permission: {e}")
        return False


if __name__ == "__main__":
    import fire

    def check():
        """Check all permission statuses."""
        state = check_all_permissions()
        return state.model_dump()

    def check_one(permission: str):
        """Check a specific permission status."""
        try:
            perm = Permission(permission)
        except ValueError:
            return {"error": f"Unknown permission: {permission}"}
        state = check_permission(perm)
        return state.model_dump()

    def instructions(permission: str):
        """Get instructions for a permission."""
        try:
            perm = Permission(permission)
        except ValueError:
            return {"error": f"Unknown permission: {permission}"}
        return get_permission_instructions(perm)

    def open_settings(permission: str):
        """Open system preferences for a permission."""
        try:
            perm = Permission(permission)
        except ValueError:
            return {"error": f"Unknown permission: {permission}"}
        success = open_system_preferences(perm)
        return {"opened": success}

    fire.Fire(
        {
            "check": check,
            "check_one": check_one,
            "instructions": instructions,
            "open": open_settings,
        }
    )
