#!/usr/bin/env python3
"""Start Streamlit, wait for readiness, and open the local app in a browser."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8501
STARTUP_TIMEOUT_SECONDS = 120
PORT_SEARCH_ATTEMPTS = 10


def app_url(host: str, port: int) -> str:
    browser_host = "localhost" if host == "127.0.0.1" else host
    return f"http://{browser_host}:{port}"


def is_healthy(host: str, port: int) -> bool:
    try:
        with urlopen(
            f"http://{host}:{port}/_stcore/health",
            timeout=1,
        ) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def is_port_available(host: str, port: int) -> bool:
    """Check whether the launcher can bind a local TCP port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
        return True
    except OSError:
        return False


def select_available_port(
    host: str,
    preferred_port: int,
    attempts: int = PORT_SEARCH_ATTEMPTS,
) -> int:
    """Use the requested port or the next available local port."""
    if not 1 <= preferred_port <= 65_535:
        raise ValueError("port must be between 1 and 65535")
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    final_port = min(preferred_port + attempts - 1, 65_535)
    for port in range(preferred_port, final_port + 1):
        if is_port_available(host, port):
            return port
    raise RuntimeError(
        f"No available local port was found from {preferred_port} to {final_port}"
    )


def wait_until_ready(
    process: subprocess.Popen,
    host: str,
    port: int,
    timeout: int = STARTUP_TIMEOUT_SECONDS,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if is_healthy(host, port):
            return True
        time.sleep(0.5)
    return False


def stop_process(process: subprocess.Popen, timeout: int = 10) -> int:
    """Stop a child process and wait so no background process is orphaned."""
    if process.poll() is None:
        process.terminate()
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        import streamlit  # noqa: F401

        print("Application launcher check passed.")
        return 0

    try:
        selected_port = select_available_port(args.host, args.port)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}")
        return 1
    if selected_port != args.port:
        print(
            f"Port {args.port} is already in use. "
            f"Starting this app on port {selected_port} instead."
        )
    url = app_url(args.host, selected_port)

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address",
        args.host,
        "--server.port",
        str(selected_port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    print("Starting Complexation Property Explorer...")
    try:
        process = subprocess.Popen(command, cwd=PROJECT_ROOT)  # noqa: S603
    except OSError as error:
        print(f"ERROR: Could not start the local app: {error}")
        return 1
    try:
        if not wait_until_ready(process, args.host, selected_port):
            return_code = process.poll()
            if return_code is None:
                stop_process(process)
                print("ERROR: The local app did not become ready within two minutes.")
            else:
                print(f"ERROR: The local app exited during startup (code {return_code}).")
            return return_code if return_code not in (None, 0) else 1

        print(f"Ready: {url}")
        if not args.no_browser:
            if webbrowser.open(url, new=2):
                print("Opened the app in the default browser.")
            else:
                print(f"Open this address in a browser: {url}")
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping the local app...")
        stop_process(process)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
