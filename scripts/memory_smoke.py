#!/usr/bin/env python3
"""Measure the snapshot-only web process under repeated public-route traffic."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROUTES = ("/", "/api/signals", "/breadth", "/api/breadth")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _rss_mib(pid: int) -> float:
    status = Path(f"/proc/{pid}/status")
    if status.exists():
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    output = subprocess.check_output(
        ["ps", "-o", "rss=", "-p", str(pid)], text=True
    ).strip()
    if not output:
        raise RuntimeError(f"could not read RSS for process {pid}")
    return int(output) / 1024


def _get(url: str) -> int:
    try:
        with urlopen(url, timeout=5) as response:
            response.read()
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--limit-mib", type=float, default=256)
    parser.add_argument("--growth-limit-mib", type=float, default=16)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    port = _free_port()
    env = {**os.environ, "DATA_DIR": str(root / "data")}
    descriptor, log_name = tempfile.mkstemp(prefix="mvs-memory-egress-", suffix=".jsonl")
    os.close(descriptor)
    egress_log = Path(log_name)
    env["EGRESS_LOG"] = str(egress_log)
    process = subprocess.Popen(
        [
            sys.executable,
            str(root / "scripts" / "network_guard.py"),
            "--",
            "uvicorn",
            "live_stock_signal_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(process.stderr.read())
            try:
                if _get(base + "/") == 200:
                    break
            except URLError:
                time.sleep(0.1)
        else:
            raise RuntimeError("uvicorn did not become ready")

        startup = _rss_mib(process.pid)
        samples = []
        for _ in range(args.iterations):
            for route in ROUTES:
                status = _get(base + route)
                if status != 200:
                    raise RuntimeError(f"{route} returned HTTP {status}")
            samples.append(_rss_mib(process.pid))
        peak = max([startup, *samples])
        peak_growth = peak - startup
        final_growth = samples[-1] - startup
        print(
            f"startup_rss_mib={startup:.2f} peak_rss_mib={peak:.2f} "
            f"final_rss_mib={samples[-1]:.2f} peak_growth_mib={peak_growth:.2f} "
            f"final_growth_mib={final_growth:.2f}"
        )
        if peak >= args.limit_mib:
            raise RuntimeError(f"peak RSS {peak:.2f} MiB exceeds {args.limit_mib:.2f} MiB")
        if peak_growth > args.growth_limit_mib:
            raise RuntimeError(
                f"peak RSS growth {peak_growth:.2f} MiB exceeds "
                f"{args.growth_limit_mib:.2f} MiB"
            )
        if egress_log.exists() and egress_log.stat().st_size:
            raise RuntimeError(
                f"web process attempted blocked egress: {egress_log.read_text()}"
            )
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        egress_log.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
