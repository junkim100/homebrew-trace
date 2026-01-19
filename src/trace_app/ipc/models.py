"""IPC request/response models for Python-Electron communication."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IPCMethod(str, Enum):
    """Available IPC methods."""

    PING = "ping"
    GET_STATUS = "get_status"
    SHUTDOWN = "shutdown"
    # Permission methods
    PERMISSIONS_CHECK_ALL = "permissions.check_all"
    PERMISSIONS_CHECK = "permissions.check"
    PERMISSIONS_GET_INSTRUCTIONS = "permissions.get_instructions"
    PERMISSIONS_OPEN_SETTINGS = "permissions.open_settings"
    PERMISSIONS_REQUEST_ACCESSIBILITY = "permissions.request_accessibility"
    PERMISSIONS_REQUEST_LOCATION = "permissions.request_location"
    # Service management methods
    SERVICES_GET_HEALTH = "services.get_health"
    SERVICES_RESTART = "services.restart"
    SERVICES_TRIGGER_BACKFILL = "services.trigger_backfill"
    SERVICES_CHECK_MISSING = "services.check_missing"


class IPCRequest(BaseModel):
    """Request model for IPC communication."""

    id: str = Field(..., description="Unique request identifier")
    method: str = Field(..., description="Method to invoke")
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters")


class IPCResponse(BaseModel):
    """Response model for IPC communication."""

    id: str = Field(..., description="Request identifier this response corresponds to")
    success: bool = Field(..., description="Whether the request succeeded")
    result: Any = Field(default=None, description="Result data if successful")
    error: str | None = Field(default=None, description="Error message if failed")


class BackendStatus(BaseModel):
    """Status information about the Python backend."""

    version: str = Field(..., description="Backend version")
    running: bool = Field(default=True, description="Whether the backend is running")
    uptime_seconds: float = Field(..., description="Seconds since backend started")
    python_version: str = Field(..., description="Python version")
    capture_stats: dict[str, Any] | None = Field(
        default=None, description="Capture daemon statistics"
    )
    service_health: dict[str, Any] | None = Field(
        default=None, description="Health status of all services"
    )
