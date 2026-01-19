"""Command-line interface for Trace."""

import fire

from src.trace_app.ipc.server import run_server


class TraceCLI:
    """Trace CLI commands."""

    def serve(self) -> None:
        """Start the IPC server for Electron communication.

        This command starts the Python backend server that communicates with
        the Electron frontend via stdin/stdout JSON protocol.
        """
        run_server()


def main() -> None:
    """Main entry point for the Trace CLI."""
    fire.Fire(TraceCLI)


if __name__ == "__main__":
    main()
