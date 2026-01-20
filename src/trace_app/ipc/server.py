"""IPC server for Python-Electron communication.

This module implements a JSON-RPC-like protocol over stdin/stdout for
communication between the Electron main process and the Python backend.

Protocol:
- Each message is a single line of JSON terminated by newline
- Request format: {"id": "...", "method": "...", "params": {...}}
- Response format: {"id": "...", "success": true/false, "result": ..., "error": ...}
"""

import json
import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from src.core.services import ServiceManager
from src.trace_app import __version__
from src.trace_app.ipc.models import BackendStatus, IPCRequest, IPCResponse

logger = logging.getLogger(__name__)


# Import handlers to register them (must be after handler registry is defined)
# These imports are done at module level to ensure handlers are registered
def _register_handlers() -> None:
    """Register all IPC handlers from handler modules."""
    # Import handler modules to trigger @handler decorator registration
    from src.trace_app.ipc import (  # noqa: F401
        blocklist_handlers,
        chat_handlers,
        export_handlers,
        graph_handlers,
        open_loops_handlers,
        permissions_handlers,
        service_handlers,
        spotlight_handlers,
    )


# Global state for the server
_start_time: float = 0.0
_running: bool = False
_service_manager: ServiceManager | None = None


# Handler registry
_handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}


def handler(method: str) -> Callable:
    """Decorator to register an IPC method handler."""

    def decorator(func: Callable[[dict[str, Any]], Any]) -> Callable:
        _handlers[method] = func
        return func

    return decorator


@handler("ping")
def handle_ping(params: dict[str, Any]) -> str:
    """Simple ping handler for connection testing."""
    return "pong"


@handler("get_status")
def handle_get_status(params: dict[str, Any]) -> dict[str, Any]:
    """Return backend status information."""
    capture_stats = None
    service_health = None

    if _service_manager:
        # Get capture stats if daemon is running
        if _service_manager._capture_daemon:
            stats = _service_manager._capture_daemon.get_stats()
            capture_stats = {
                "captures_total": stats.captures_total,
                "screenshots_captured": stats.screenshots_captured,
                "screenshots_deduplicated": stats.screenshots_deduplicated,
                "events_created": stats.events_created,
                "errors": stats.errors,
            }

        # Get service health
        service_health = _service_manager.get_health_status()

    status = BackendStatus(
        version=__version__,
        running=_running,
        uptime_seconds=time.time() - _start_time,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        capture_stats=capture_stats,
        service_health=service_health,
    )
    return status.model_dump()


@handler("shutdown")
def handle_shutdown(params: dict[str, Any]) -> str:
    """Signal the server to shut down gracefully."""
    global _running
    _running = False
    return "shutting_down"


def process_request(request_data: dict[str, Any]) -> IPCResponse:
    """Process a single IPC request and return a response."""
    try:
        request = IPCRequest.model_validate(request_data)
    except Exception as e:
        return IPCResponse(
            id=request_data.get("id", "unknown"),
            success=False,
            error=f"Invalid request format: {e}",
        )

    handler_func = _handlers.get(request.method)
    if handler_func is None:
        return IPCResponse(
            id=request.id,
            success=False,
            error=f"Unknown method: {request.method}",
        )

    try:
        result = handler_func(request.params)
        return IPCResponse(id=request.id, success=True, result=result)
    except Exception as e:
        logger.exception(f"Error handling {request.method}")
        return IPCResponse(id=request.id, success=False, error=str(e))


def send_response(response: IPCResponse) -> None:
    """Send a response to stdout."""
    line = response.model_dump_json() + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()


def run_server() -> None:
    """Run the IPC server, reading requests from stdin and writing responses to stdout.

    The server runs until it receives a shutdown request or stdin is closed.
    Starts all background services (capture, hourly, daily) via ServiceManager.
    """
    global _start_time, _running, _service_manager

    _start_time = time.time()
    _running = True

    # Configure logging to stderr to not interfere with IPC on stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    logger.info("IPC server starting")

    # Register all handlers
    _register_handlers()

    # Start all services via ServiceManager
    service_results = {}
    try:
        _service_manager = ServiceManager()
        service_results = _service_manager.start_all(notify=True)
        logger.info(f"Services started: {service_results}")
    except Exception as e:
        logger.error(f"Failed to start services: {e}")
        _service_manager = None

    # Signal readiness to parent process
    ready_msg = {
        "type": "ready",
        "version": __version__,
        "services": service_results,
    }
    sys.stdout.write(json.dumps(ready_msg) + "\n")
    sys.stdout.flush()

    try:
        while _running:
            try:
                line = sys.stdin.readline()
                if not line:
                    # EOF - parent process closed stdin
                    logger.info("stdin closed, shutting down")
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request_data = json.loads(line)
                except json.JSONDecodeError as e:
                    error_response = IPCResponse(
                        id="unknown",
                        success=False,
                        error=f"Invalid JSON: {e}",
                    )
                    send_response(error_response)
                    continue

                response = process_request(request_data)
                send_response(response)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt, shutting down")
                break

    finally:
        # Stop all services
        if _service_manager:
            logger.info("Stopping all services...")
            _service_manager.stop_all()
        logger.info("IPC server stopped")
