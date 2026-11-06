"""The addresses `graphtyn serve` listens on.

Loopback serves the browser on the same machine. An agent in a VM or a container reaches
the host through a private interface instead (a libvirt or Docker bridge), so the server can listen on both at once without `0.0.0.0`, which would
also expose it to the local network.
"""
from __future__ import annotations

import re
import socket
import sys
from typing import Iterable

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_HOST = re.compile(r"[A-Za-z0-9._:-]+")
# Linux lets a socket bind an address whose interface is not up yet (a VM bridge at login).
_IP_FREEBIND = getattr(socket, "IP_FREEBIND", 15)


def listen_hosts(values: Iterable[str] | str | None) -> list[str]:
    """Hosts from repeated or comma-separated `--host` values, in order and without repeats."""
    values = [values] if isinstance(values, str) else list(values or [])
    hosts: list[str] = []
    for value in values:
        for host in str(value).split(","):
            host = host.strip()
            if not host:
                continue
            if not _HOST.fullmatch(host):
                raise ValueError(f"host de servicio inválido: {host}")
            if host not in hosts:
                hosts.append(host)
    return hosts or ["127.0.0.1"]


def browser_host(hosts: list[str]) -> str:
    """Where the dashboard opens on this machine."""
    return next((host for host in hosts if host in LOOPBACK), "127.0.0.1" if hosts[0] in {"0.0.0.0", "::"} else hosts[0])


def bind_socket(host: str, port: int) -> socket.socket:
    """A bound TCP socket for one listen address, ready for `uvicorn.Server.run(sockets=...)`."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    elif sys.platform.startswith("linux") and host not in LOOPBACK:
        try:
            sock.setsockopt(socket.SOL_IP, _IP_FREEBIND, 1)
        except OSError:
            pass
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    sock.set_inheritable(True)
    return sock
