"""IPC handlers for blocklist management.

Provides handlers for:
- Listing blocklist entries
- Adding apps/domains to blocklist
- Removing entries from blocklist
- Toggling entry enabled state

P10-01: Selective capture blocklist
"""

import logging
from typing import Any

from src.capture.blocklist import BlocklistManager, initialize_default_blocklist
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


# Singleton blocklist manager
_blocklist_manager: BlocklistManager | None = None


def _get_manager() -> BlocklistManager:
    """Get or create the blocklist manager."""
    global _blocklist_manager
    if _blocklist_manager is None:
        _blocklist_manager = BlocklistManager()
    return _blocklist_manager


@handler("blocklist.list")
def handle_list_blocklist(params: dict[str, Any]) -> dict[str, Any]:
    """List all blocklist entries.

    Params:
        include_disabled: Whether to include disabled entries (default: True)
    """
    include_disabled = params.get("include_disabled", True)
    manager = _get_manager()

    entries = manager.list_entries(include_disabled=include_disabled)

    return {
        "success": True,
        "entries": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@handler("blocklist.add_app")
def handle_add_app(params: dict[str, Any]) -> dict[str, Any]:
    """Add an app to the blocklist.

    Params:
        bundle_id: The app's bundle identifier (required)
        display_name: Human-readable name (optional)
        block_screenshots: Whether to block screenshots (default: True)
        block_events: Whether to block events (default: True)
    """
    bundle_id = params.get("bundle_id")
    if not bundle_id:
        return {
            "success": False,
            "error": "Missing 'bundle_id' parameter",
        }

    display_name = params.get("display_name")
    block_screenshots = params.get("block_screenshots", True)
    block_events = params.get("block_events", True)

    manager = _get_manager()

    try:
        entry = manager.add_app(
            bundle_id=bundle_id,
            display_name=display_name,
            block_screenshots=block_screenshots,
            block_events=block_events,
        )

        return {
            "success": True,
            "entry": entry.to_dict(),
        }
    except Exception as e:
        logger.error(f"Failed to add app to blocklist: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("blocklist.add_domain")
def handle_add_domain(params: dict[str, Any]) -> dict[str, Any]:
    """Add a domain to the blocklist.

    Params:
        domain: The domain to block (required)
        display_name: Human-readable name (optional)
        block_screenshots: Whether to block screenshots (default: True)
        block_events: Whether to block events (default: True)
    """
    domain = params.get("domain")
    if not domain:
        return {
            "success": False,
            "error": "Missing 'domain' parameter",
        }

    display_name = params.get("display_name")
    block_screenshots = params.get("block_screenshots", True)
    block_events = params.get("block_events", True)

    manager = _get_manager()

    try:
        entry = manager.add_domain(
            domain=domain,
            display_name=display_name,
            block_screenshots=block_screenshots,
            block_events=block_events,
        )

        return {
            "success": True,
            "entry": entry.to_dict(),
        }
    except Exception as e:
        logger.error(f"Failed to add domain to blocklist: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("blocklist.remove")
def handle_remove_blocklist_entry(params: dict[str, Any]) -> dict[str, Any]:
    """Remove an entry from the blocklist.

    Params:
        blocklist_id: The ID of the entry to remove (required)
    """
    blocklist_id = params.get("blocklist_id")
    if not blocklist_id:
        return {
            "success": False,
            "error": "Missing 'blocklist_id' parameter",
        }

    manager = _get_manager()

    try:
        removed = manager.remove_entry(blocklist_id)

        return {
            "success": True,
            "removed": removed,
        }
    except Exception as e:
        logger.error(f"Failed to remove blocklist entry: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("blocklist.set_enabled")
def handle_set_blocklist_enabled(params: dict[str, Any]) -> dict[str, Any]:
    """Enable or disable a blocklist entry.

    Params:
        blocklist_id: The ID of the entry (required)
        enabled: Whether to enable the entry (required)
    """
    blocklist_id = params.get("blocklist_id")
    if not blocklist_id:
        return {
            "success": False,
            "error": "Missing 'blocklist_id' parameter",
        }

    enabled = params.get("enabled")
    if enabled is None:
        return {
            "success": False,
            "error": "Missing 'enabled' parameter",
        }

    manager = _get_manager()

    try:
        updated = manager.set_enabled(blocklist_id, bool(enabled))

        return {
            "success": True,
            "updated": updated,
        }
    except Exception as e:
        logger.error(f"Failed to update blocklist entry: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("blocklist.init_defaults")
def handle_init_default_blocklist(params: dict[str, Any]) -> dict[str, Any]:
    """Initialize the blocklist with default sensitive apps and domains.

    This adds common password managers and banking sites to the blocklist.
    """
    try:
        count = initialize_default_blocklist()

        return {
            "success": True,
            "added": count,
        }
    except Exception as e:
        logger.error(f"Failed to initialize default blocklist: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("blocklist.check")
def handle_check_blocked(params: dict[str, Any]) -> dict[str, Any]:
    """Check if an app or domain is currently blocked.

    Params:
        bundle_id: App bundle ID to check (optional)
        url: URL to check (optional)
    """
    bundle_id = params.get("bundle_id")
    url = params.get("url")

    if not bundle_id and not url:
        return {
            "success": False,
            "error": "At least one of 'bundle_id' or 'url' is required",
        }

    manager = _get_manager()

    try:
        is_blocked, reason = manager.should_block_capture(
            bundle_id=bundle_id,
            url=url,
        )

        return {
            "success": True,
            "blocked": is_blocked,
            "reason": reason,
        }
    except Exception as e:
        logger.error(f"Failed to check blocklist: {e}")
        return {
            "success": False,
            "error": str(e),
        }
