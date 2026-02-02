"""
Shared utilities for Chain Guru scripts.
Provides secure SSL context handling and common helper functions.
"""

import os
import ssl
import ipaddress
import socket
import urllib.parse
from typing import Tuple, Optional


def get_ssl_context() -> Optional[ssl.SSLContext]:
    """
    Get SSL context with secure defaults.
    Only disables verification if INSECURE_SSL env var is explicitly set.
    
    Returns:
        SSLContext with secure defaults, or None for system defaults
    """
    if os.environ.get("INSECURE_SSL", "").lower() in ("1", "true", "yes"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def is_private_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if IP address is private/reserved."""
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_reserved
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
    )


def is_safe_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL to prevent SSRF attacks.
    Blocks private IPs, localhost, and internal networks.
    
    Args:
        url: URL to validate
        
    Returns:
        Tuple of (is_safe, error_reason)
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        return False, f"invalid_url:{e}"

    if parsed.scheme not in ("http", "https"):
        return False, "invalid_scheme"

    host = parsed.hostname
    if not host:
        return False, "missing_host"

    host_lower = host.strip(".").lower()
    
    # Block localhost variations
    if (
        host_lower == "localhost"
        or host_lower.endswith(".localhost")
        or host_lower.endswith(".local")
        or host_lower in ("localhost.localdomain", "ip6-localhost", "ip6-loopback")
    ):
        return False, "localhost_blocked"

    # Check if host is an IP address
    try:
        ip_obj = ipaddress.ip_address(host_lower)
        if is_private_ip(ip_obj):
            return False, "private_ip_blocked"
        return True, None
    except ValueError:
        pass  # Not an IP, continue with DNS check

    # DNS resolution check
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, "dns_error"

    for info in infos:
        addr = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if is_private_ip(ip_obj):
            return False, "private_ip_blocked"

    return True, None


def clean_number(s: str) -> float:
    """Clean and parse number string, handling commas."""
    try:
        return float(s.replace(',', '').strip())
    except (ValueError, AttributeError):
        return 0.0
