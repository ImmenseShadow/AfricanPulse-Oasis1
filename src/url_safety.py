"""Helpers that keep externally supplied feed URLs from reaching private networks and from
leaking tokens into pages or logs."""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlsplit

BLOCKED_HOST_NAMES = {"localhost", "metadata.google.internal", "metadata"}
BLOCKED_HOST_SUFFIXES = (".localhost", ".internal", ".local", ".localdomain")


class UnsafeDestinationError(Exception):
    """A URL points somewhere the collector must never connect to."""


def is_blocked_host_name(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    return lowered in BLOCKED_HOST_NAMES or lowered.endswith(BLOCKED_HOST_SUFFIXES)


def is_public_ip(address: str) -> bool:
    """True only for globally routable addresses (not loopback, private, link-local, metadata...)."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


def resolve_ips(host: str, port: int) -> list[str]:
    """Every address the host name currently resolves to."""
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def check_destination(url: str, allow_private: bool = False) -> None:
    """Raise UnsafeDestinationError unless the URL is http(s) and every resolved address is public.

    Called for the original URL and again for every redirect target. Messages never include the URL."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise UnsafeDestinationError("The feed address is not a valid http or https URL.")
    if parts.username or parts.password:
        raise UnsafeDestinationError("The feed address is not a valid http or https URL.")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeDestinationError("The feed address is not a valid http or https URL.") from exc
    if port is not None and (port <= 0 or port > 65535):
        raise UnsafeDestinationError("The feed address is not a valid http or https URL.")
    if allow_private:
        return
    host = parts.hostname
    if is_blocked_host_name(host):
        raise UnsafeDestinationError("Feeds on localhost or private network addresses are not allowed.")
    chosen_port = port or (443 if parts.scheme.lower() == "https" else 80)
    try:
        addresses = resolve_ips(host, chosen_port)
    except (socket.gaierror, UnicodeError, OSError):
        raise UnsafeDestinationError("The feed host name could not be resolved.")
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise UnsafeDestinationError("Feeds on localhost or private network addresses are not allowed.")


def mask_url(url: Optional[str]) -> str:
    """Shortened form for display: scheme, host and the first two path segments. Feed tokens are
    normally carried in the later path segments or the query string, so they are hidden."""
    parts = urlsplit((url or "").strip())
    if not parts.scheme or not parts.netloc:
        return "(hidden)"
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    segments = [s for s in parts.path.split("/") if s]
    shown = "/".join(segments[:2])
    hidden = len(segments) > 2 or bool(parts.query)
    text = f"{parts.scheme}://{host}"
    if shown:
        text += "/" + shown
    if hidden:
        text += "/…"
    return text
