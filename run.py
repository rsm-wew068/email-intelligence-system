#!/usr/bin/env python3
"""
Launcher script for NexusAI Email Intelligence System.
Automatically selects the Python environment containing FastAPI/Uvicorn,
supports CLI port arguments, and automatically finds a free port if the
requested port is already in use.
"""
import os
import sys
import socket

CONDA_PYTHON = "/opt/homebrew/Caskroom/miniconda/base/bin/python3"

try:
    import uvicorn  # noqa: F401
    import fastapi  # noqa: F401
    import networkx  # noqa: F401
except ModuleNotFoundError:
    if os.path.exists(CONDA_PYTHON) and os.path.realpath(sys.executable) != os.path.realpath(CONDA_PYTHON):
        print(f"[Launcher] Switching to Miniconda Python environment: {CONDA_PYTHON}")
        os.execv(CONDA_PYTHON, [CONDA_PYTHON, "-s", __file__] + sys.argv[1:])
    else:
        raise


def is_port_free(host: str, port: int) -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, starting_port: int, max_attempts: int = 20) -> int:
    """Find the next available port starting from starting_port."""
    for candidate in range(starting_port, starting_port + max_attempts):
        if is_port_free(host, candidate):
            return candidate
    return starting_port


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")

    # Parse port from arguments or environment
    requested_port = 8000
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--port", "-p") and len(sys.argv) > 2:
            try:
                requested_port = int(sys.argv[2])
            except ValueError:
                pass
        else:
            try:
                requested_port = int(sys.argv[1])
            except ValueError:
                pass
    elif "PORT" in os.environ:
        try:
            requested_port = int(os.environ["PORT"])
        except ValueError:
            pass

    # Check port availability and auto-fallback if busy
    if not is_port_free(host, requested_port):
        alt_port = find_available_port(host, requested_port + 1)
        print(f"⚠️  Port {requested_port} is already in use!")
        print(f"🔄 Auto-switching to available port: {alt_port}")
        port = alt_port
    else:
        port = requested_port

    print(f"\n🚀 NexusAI Email Intelligence System starting at http://{host}:{port}\n")
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
