from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def validate_outbound_url(url: str, allowed_hosts: frozenset[str]) -> None:
    """Fail closed on unsafe URLs and DNS answers for outbound HTTP(S)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials")

    host = parsed.hostname.lower().rstrip(".")
    allowed = {item.strip().lower().rstrip(".") for item in allowed_hosts if item.strip()}
    if host not in allowed:
        raise ValueError("URL host is not allow-listed")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public_address(literal):
            raise ValueError("URL resolves to a non-public IP address")
        return

    try:
        answers = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("URL hostname could not be resolved safely") from exc
    if not answers:
        raise ValueError("URL hostname has no usable address")
    for answer in answers:
        address = answer[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("URL hostname returned an invalid address") from exc
        if not _is_public_address(ip):
            raise ValueError("URL hostname resolves to a non-public IP address")


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
