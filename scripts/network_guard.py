#!/usr/bin/env python3
"""Run uvicorn with process-wide outbound network connections disabled."""

from __future__ import annotations

import ipaddress
import json
import os
import runpy
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


def _is_local(address: Any) -> bool:
    if isinstance(address, str):
        return True  # Unix-domain socket path.
    if not isinstance(address, tuple) or not address:
        return False
    host = str(address[0]).strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _record_block(address: Any) -> None:
    log_path = os.environ.get("EGRESS_LOG")
    if not log_path:
        return
    host = address[0] if isinstance(address, tuple) and address else str(address)
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "host": str(host),
        "address": repr(address),
    }
    with Path(log_path).open("a", encoding="utf-8") as target:
        target.write(json.dumps(entry, separators=(",", ":")) + "\n")


def install_network_guard() -> None:
    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        if not _is_local(address):
            _record_block(address)
            raise PermissionError(f"snapshot web runtime blocked outbound connect: {address!r}")
        return _ORIGINAL_CONNECT(sock, address)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not _is_local(address):
            _record_block(address)
            raise PermissionError(f"snapshot web runtime blocked outbound connect: {address!r}")
        return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.create_connection = guarded_create_connection


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    install_network_guard()
    if args == ["--probe-external"]:
        try:
            socket.create_connection(("203.0.113.1", 443), timeout=0.01)
        except PermissionError:
            return 0
        raise RuntimeError("external-connect probe unexpectedly escaped network guard")
    if args[:1] == ["--"]:
        args = args[1:]
    if not args or args[0] != "uvicorn":
        raise SystemExit("usage: network_guard.py -- uvicorn MODULE:APP [OPTIONS]")
    sys.argv = ["uvicorn", *args[1:]]
    runpy.run_module("uvicorn", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
