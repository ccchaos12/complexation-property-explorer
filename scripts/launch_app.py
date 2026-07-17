#!/usr/bin/env python3
"""Start Streamlit, wait for readiness, and open the local app in a browser."""

from __future__ import annotations

import argparse
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

    url = app_url(args.host, args.port)
    if is_healthy(args.host, args.port):
        print(f"The app is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url, new=2)
        return 0

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    print("Starting Complexation Property Explorer...")
    process = subprocess.Popen(command, cwd=PROJECT_ROOT)
    try:
        if not wait_until_ready(process, args.host, args.port):
            if process.poll() is None:
                process.terminate()
            print("ERROR: The local app did not become ready within two minutes.")
            return process.returncode or 1

        print(f"Ready: {url}")
        if not args.no_browser:
            if webbrowser.open(url, new=2):
                print("Opened the app in the default browser.")
            else:
                print(f"Open this address in a browser: {url}")
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping the local app...")
        process.terminate()
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
