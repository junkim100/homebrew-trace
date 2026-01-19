"""IPC handlers for service management.

Provides handlers for:
- Getting service health status
- Restarting individual services
- Triggering backfill operations
"""

import logging
from typing import Any

from src.trace_app.ipc.server import _service_manager, handler

logger = logging.getLogger(__name__)


@handler("services.get_health")
def handle_get_service_health(params: dict[str, Any]) -> dict[str, Any]:
    """Get health status of all services."""
    if _service_manager is None:
        return {
            "healthy": False,
            "error": "Service manager not initialized",
            "services": {},
        }

    return _service_manager.get_health_status()


@handler("services.restart")
def handle_restart_service(params: dict[str, Any]) -> dict[str, Any]:
    """Restart a specific service.

    Params:
        service: Name of service to restart ('capture', 'hourly', 'daily')
    """
    if _service_manager is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    service_name = params.get("service")
    if not service_name:
        return {
            "success": False,
            "error": "Missing 'service' parameter",
        }

    if service_name not in ("capture", "hourly", "daily"):
        return {
            "success": False,
            "error": f"Unknown service: {service_name}",
        }

    success = _service_manager.restart_service(service_name)

    return {
        "success": success,
        "service": service_name,
    }


@handler("services.trigger_backfill")
def handle_trigger_backfill(params: dict[str, Any]) -> dict[str, Any]:
    """Manually trigger backfill for missing notes.

    Params:
        notify: Whether to send notifications (default: True)
    """
    if _service_manager is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    notify = params.get("notify", True)

    try:
        result = _service_manager.trigger_backfill(notify=notify)

        return {
            "success": True,
            "hours_checked": result.hours_checked,
            "hours_missing": result.hours_missing,
            "hours_backfilled": result.hours_backfilled,
            "hours_failed": result.hours_failed,
        }

    except Exception as e:
        logger.error(f"Backfill trigger failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.check_missing")
def handle_check_missing(params: dict[str, Any]) -> dict[str, Any]:
    """Check for ALL missing hourly notes without triggering backfill.

    Scans entire database for hours with activity but no notes.
    """
    if _service_manager is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    try:
        if _service_manager._backfill_detector is None:
            from src.jobs.backfill import BackfillDetector

            _service_manager._backfill_detector = BackfillDetector(
                db_path=_service_manager.db_path,
                api_key=_service_manager.api_key,
            )

        missing = _service_manager._backfill_detector.find_missing_hours()

        return {
            "success": True,
            "missing_count": len(missing),
            "missing_hours": [h.isoformat() for h in missing],
        }

    except Exception as e:
        logger.error(f"Missing hours check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
