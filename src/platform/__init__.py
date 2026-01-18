"""Platform-specific functionality for Trace."""

from .permissions import (
    Permission,
    PermissionStatus,
    check_all_permissions,
    check_permission,
    get_permission_instructions,
    open_system_preferences,
    request_accessibility_permission,
    request_location_permission,
)

__all__ = [
    "Permission",
    "PermissionStatus",
    "check_permission",
    "check_all_permissions",
    "get_permission_instructions",
    "open_system_preferences",
    "request_accessibility_permission",
    "request_location_permission",
]
