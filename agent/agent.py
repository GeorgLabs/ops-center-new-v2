#!/usr/bin/env python3
"""Ops Center agent - measures THIS computer and reports to an Ops Center server.

Standalone: this folder is all you need on the machine you want to watch (Python 3.9+ and psutil).

    pip install -r requirements.txt
    python agent.py --url https://ops.example.com --key-file ~/.ops-agent-key

Settings (command line wins over environment):
    --url         OPS_URL        server address, default http://127.0.0.1:8000
    --key         OPS_KEY        the host's API key (ops_...)   [visible in `ps`; prefer the next two]
    --key-file    OPS_KEY_FILE   file that contains the key
    --every       OPS_INTERVAL   seconds between reports, default 5
    --once                       send one report and exit (good for cron / testing)

Exit codes: 0 normal stop (Ctrl+C / SIGTERM, or --once succeeded) | 1 --once failed | 2 bad settings or the
server rejected the key (retrying would be pointless).
The key identifies the host and travels in the X-API-Key header, never in the URL.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

try:
    import psutil
except ImportError:
    sys.exit("psutil is missing: run  pip install -r requirements.txt  (or  pip install psutil)")

DEFAULT_URL = "http://127.0.0.1:8000"
MAX_BACKOFF = 60.0
stop = threading.Event()  # set by Ctrl+C / SIGTERM; waiting on it doubles as an interruptible sleep


class Rejected(Exception):
    """The server understood us and said no (401/403): the key is wrong or the host was deleted."""


def disk_path() -> str:
    return psutil.disk_partitions()[0].mountpoint if sys.platform == "win32" else "/"


def measure() -> dict:
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage(disk_path()).percent,
    }


def send(url: str, key: str, data: dict, timeout: float = 10) -> str:
    """POST one measurement. Returns a short status text; raises Rejected on 401/403, OSError otherwise."""
    request = urllib.request.Request(  # noqa: S310 - scheme is validated in main()
        url.rstrip("/") + "/api/ingest",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise Rejected(f"the server rejected the API key (HTTP {exc.code})") from None
        raise OSError(f"HTTP {exc.code} {exc.read().decode(errors='replace')[:200]}") from None
    except urllib.error.URLError as exc:
        raise OSError(f"cannot reach server ({exc.reason})") from None


def read_key(args: argparse.Namespace) -> str:
    key = args.key or os.environ.get("OPS_KEY", "")
    key_file = args.key_file or os.environ.get("OPS_KEY_FILE", "")
    if not key and key_file:
        try:
            with open(os.path.expanduser(key_file), encoding="utf-8") as handle:
                key = handle.read().strip()
        except OSError as exc:
            sys.exit(f"cannot read the key file: {exc}")
    if not key:
        sys.exit("No API key. Use --key-file FILE (or --key / OPS_KEY). You get the key when you add a host in Ops Center.")
    return key.strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report this machine's load to Ops Center", epilog=__doc__.split("\n\n")[1])
    parser.add_argument("--url", default=os.environ.get("OPS_URL", DEFAULT_URL))
    parser.add_argument("--key", help="the host's API key (ops_...)")
    parser.add_argument("--key-file", help="file containing the API key")
    parser.add_argument("--every", type=float, default=float(os.environ.get("OPS_INTERVAL", 5)), help="seconds between reports")
    parser.add_argument("--once", action="store_true", help="send one report and exit")
    return parser.parse_args(argv)


def run(url: str, key: str, every: float, once: bool = False) -> int:
    failures = 0
    while not stop.is_set():
        data = measure()
        stamp = time.strftime("%H:%M:%S")
        try:
            status = send(url, key, data)
            failures = 0
            print(f"{stamp}  cpu {data['cpu_percent']:5.1f}%  mem {data['memory_percent']:5.1f}%  "
                  f"disk {data['disk_percent']:5.1f}%  -> {status}", flush=True)
            if once:
                return 0
            delay = max(0.0, every - 1)  # measure() already took ~1s
        except Rejected as exc:
            print(f"{stamp}  {exc}. Check the key (or the host still exists). Stopping.", file=sys.stderr, flush=True)
            return 2
        except OSError as exc:
            failures += 1
            delay = min(MAX_BACKOFF, every * 2**min(failures, 6))  # 10s, 20s, 40s ... max 60s
            print(f"{stamp}  {exc} - retrying in {delay:.0f}s", file=sys.stderr, flush=True)
            if once:
                return 1
        stop.wait(delay)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    url = args.url.rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        sys.exit(f"--url must look like https://host[:port], got: {args.url}")
    if args.every < 1:
        sys.exit("--every must be at least 1 second")
    key = read_key(args)
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: plain http - the API key travels unencrypted. Use https outside your own computer.", file=sys.stderr)

    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    print(f"Reporting to {url} every {args.every:g}s - Ctrl+C to stop", flush=True)
    code = run(url, key, args.every, args.once)
    if code == 0 and not args.once:
        print("bye")
    return code


if __name__ == "__main__":
    sys.exit(main())
