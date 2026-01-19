"""IPC handlers for permission management.

This module registers IPC handlers for checking and requesting macOS permissions
from the Electron frontend.
"""

import logging
from typing import Any

from src.platform.permissions import (
    Permission,
    check_all_permissions,
    check_permission,
    get_permission_instructions,
    open_system_preferences,
    request_accessibility_permission,
    request_location_permission,
)
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("permissions.check_all")
def handle_check_all_permissions(params: dict[str, Any]) -> dict[str, Any]:
    """Check the status of all required permissions.

    Returns:
        Complete permission state including all permissions and whether
        all required ones are granted.
    """
    state = check_all_permissions()
    return state.model_dump()


@handler("permissions.check")
def handle_check_permission(params: dict[str, Any]) -> dict[str, Any]:
    """Check the status of a specific permission.

    Params:
        permission: The permission to check (screen_recording, accessibility, location)

    Returns:
        Permission state for the requested permission.
    """
    permission_name = params.get("permission")
    if not permission_name:
        raise ValueError("permission parameter is required")

    try:
        permission = Permission(permission_name)
    except ValueError as e:
        raise ValueError(f"Unknown permission: {permission_name}") from e

    state = check_permission(permission)
    return state.model_dump()


@handler("permissions.get_instructions")
def handle_get_instructions(params: dict[str, Any]) -> dict[str, Any]:
    """Get user-friendly instructions for granting a permission.

    Params:
        permission: The permission to get instructions for

    Returns:
        Instructions including title, description, steps, and system preferences URL.
    """
    permission_name = params.get("permission")
    if not permission_name:
        raise ValueError("permission parameter is required")

    try:
        permission = Permission(permission_name)
    except ValueError as e:
        raise ValueError(f"Unknown permission: {permission_name}") from e

    return get_permission_instructions(permission)


@handler("permissions.open_settings")
def handle_open_settings(params: dict[str, Any]) -> dict[str, Any]:
    """Open System Preferences to the relevant permission pane.

    Params:
        permission: The permission settings to open

    Returns:
        {"success": bool} indicating whether the settings were opened.
    """
    permission_name = params.get("permission")
    if not permission_name:
        raise ValueError("permission parameter is required")

    try:
        permission = Permission(permission_name)
    except ValueError as e:
        raise ValueError(f"Unknown permission: {permission_name}") from e

    success = open_system_preferences(permission)
    return {"success": success}


@handler("permissions.request_accessibility")
def handle_request_accessibility(params: dict[str, Any]) -> dict[str, Any]:
    """Trigger the system accessibility permission prompt.

    Returns:
        {"success": bool} indicating whether the prompt was triggered.
    """
    success = request_accessibility_permission()
    return {"success": success}


@handler("permissions.request_location")
def handle_request_location(params: dict[str, Any]) -> dict[str, Any]:
    """Trigger the system location permission prompt.

    Returns:
        {"success": bool} indicating whether the prompt was triggered.
    """
    success = request_location_permission()
    return {"success": success}
