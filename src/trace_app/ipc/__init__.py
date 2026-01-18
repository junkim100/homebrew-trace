"""IPC module for Python-Electron communication."""

# Import handlers to register them
import trace_app.ipc.chat_handlers  # noqa: F401
import trace_app.ipc.permissions_handlers  # noqa: F401
from trace_app.ipc.models import BackendStatus, IPCMethod, IPCRequest, IPCResponse
from trace_app.ipc.server import handler, run_server

__all__ = [
    "BackendStatus",
    "IPCMethod",
    "IPCRequest",
    "IPCResponse",
    "handler",
    "run_server",
]
