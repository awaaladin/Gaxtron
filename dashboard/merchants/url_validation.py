"""SSRF-safe callback URL validation — ported verbatim from GaX/app/core/url_validation.py."""
import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings


class CallbackUrlError(ValueError):
    pass


_BLOCKED_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"})


def validate_callback_url(url: str) -> str:
    """
    SSRF protection: only allow public HTTPS (or HTTP in dev) callback URLs.
    Blocks private IPs, link-local, and metadata endpoints — including via DNS rebinding
    (resolves the hostname and checks every returned address, not just the literal host).
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("https", "http"):
        raise CallbackUrlError("Callback URL must use http or https")

    if settings.REQUIRE_HTTPS_CALLBACKS and parsed.scheme != "https":
        raise CallbackUrlError("Callback URL must use HTTPS in production")

    if not parsed.hostname:
        raise CallbackUrlError("Callback URL must include a hostname")

    host = parsed.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise CallbackUrlError("Callback URL cannot target localhost")

    if host.endswith((".local", ".internal", ".localhost")):
        raise CallbackUrlError("Callback URL hostname not allowed")

    if host in ("169.254.169.254", "metadata.google.internal"):
        raise CallbackUrlError("Callback URL hostname not allowed")

    try:
        addr_infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise CallbackUrlError(f"Cannot resolve callback hostname: {host}") from e

    for info in addr_infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise CallbackUrlError("Callback URL cannot resolve to a private or reserved IP")

    return url
