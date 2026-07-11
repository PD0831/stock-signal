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
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_ORIGINAL_GETPEERNAME = socket.socket.getpeername
_ORIGINAL_SEND = socket.socket.send
_ORIGINAL_SENDALL = socket.socket.sendall
_ORIGINAL_SENDTO = socket.socket.sendto
_ORIGINAL_SENDMSG = getattr(socket.socket, "sendmsg", None)


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


def _record_block(operation: str, address: Any) -> None:
    log_path = os.environ.get("EGRESS_LOG")
    if not log_path:
        return
    host = address[0] if isinstance(address, tuple) and address else str(address)
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "host": str(host),
        "address": repr(address),
    }
    with Path(log_path).open("a", encoding="utf-8") as target:
        target.write(json.dumps(entry, separators=(",", ":")) + "\n")


def install_network_guard() -> None:
    def deny(operation: str, address: Any) -> None:
        _record_block(operation, address)
        raise PermissionError(
            f"snapshot web runtime blocked outbound {operation}: {address!r}"
        )

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        if not _is_local(address):
            deny("connect", address)
        return _ORIGINAL_CONNECT(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> Any:
        if not _is_local(address):
            deny("connect_ex", address)
        return _ORIGINAL_CONNECT_EX(sock, address)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not _is_local(address):
            deny("create_connection", address)
        return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        # DNS is egress too.  Only localhost and numeric loopback addresses are
        # resolved; uvicorn binds numeric addresses and does not need public DNS.
        if host is not None and not _is_local((host, 0)):
            deny("getaddrinfo", (host, 0))
        return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)

    def peer(sock: socket.socket) -> Any | None:
        try:
            return _ORIGINAL_GETPEERNAME(sock)
        except OSError:
            return None

    def guarded_send(sock: socket.socket, data: Any, *args: Any, **kwargs: Any) -> Any:
        address = peer(sock)
        if address is not None and not _is_local(address):
            deny("send", address)
        return _ORIGINAL_SEND(sock, data, *args, **kwargs)

    def guarded_sendall(sock: socket.socket, data: Any, *args: Any, **kwargs: Any) -> Any:
        address = peer(sock)
        if address is not None and not _is_local(address):
            deny("sendall", address)
        return _ORIGINAL_SENDALL(sock, data, *args, **kwargs)

    def guarded_sendto(sock: socket.socket, data: Any, *args: Any) -> Any:
        address = args[-1] if args else peer(sock)
        if address is not None and not _is_local(address):
            deny("sendto", address)
        return _ORIGINAL_SENDTO(sock, data, *args)

    def guarded_sendmsg(sock: socket.socket, buffers: Any, *args: Any) -> Any:
        address = args[2] if len(args) >= 3 else peer(sock)
        if address is not None and not _is_local(address):
            deny("sendmsg", address)
        assert _ORIGINAL_SENDMSG is not None
        return _ORIGINAL_SENDMSG(sock, buffers, *args)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.send = guarded_send
    socket.socket.sendall = guarded_sendall
    socket.socket.sendto = guarded_sendto
    if _ORIGINAL_SENDMSG is not None:
        socket.socket.sendmsg = guarded_sendmsg


def _probe_all() -> None:
    external = ("203.0.113.1", 443)
    probes = []
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probes.extend([
        lambda: tcp.connect(external),
        lambda: tcp.connect_ex(external),
        lambda: socket.create_connection(external, timeout=0.01),
        lambda: udp.sendto(b"x", external),
        lambda: socket.getaddrinfo("example.com", 443),
    ])
    if hasattr(udp, "sendmsg"):
        probes.append(lambda: udp.sendmsg([b"x"], [], 0, external))
    global _ORIGINAL_GETPEERNAME
    real_getpeername = _ORIGINAL_GETPEERNAME
    try:
        _ORIGINAL_GETPEERNAME = lambda sock: external
        probes.extend([lambda: tcp.send(b"x"), lambda: tcp.sendall(b"x")])
        for probe in probes:
            try:
                probe()
            except PermissionError:
                continue
            raise RuntimeError("adversarial egress probe unexpectedly escaped network guard")
    finally:
        _ORIGINAL_GETPEERNAME = real_getpeername
        tcp.close()
        udp.close()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    install_network_guard()
    if args == ["--probe-all"]:
        _probe_all()
        return 0
    if args[:1] == ["--"]:
        args = args[1:]
    if not args or args[0] != "uvicorn":
        raise SystemExit("usage: network_guard.py -- uvicorn MODULE:APP [OPTIONS]")
    sys.argv = ["uvicorn", *args[1:]]
    runpy.run_module("uvicorn", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
