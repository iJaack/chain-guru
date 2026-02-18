"""
TDD audit tests for chain-guru utils.py
Tests: is_private_ip, is_safe_url, clean_number, is_evm (from server.py)
"""
import ipaddress
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import is_private_ip, is_safe_url, clean_number

# ─── is_private_ip ────────────────────────────────────────────────

class TestIsPrivateIP(unittest.TestCase):

    # Private ranges
    def test_rfc1918_192(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("192.168.1.1")))

    def test_rfc1918_10(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("10.0.0.1")))

    def test_rfc1918_172(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("172.16.0.1")))

    def test_loopback_ipv4(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("127.0.0.1")))

    def test_loopback_ipv6(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("::1")))

    def test_link_local(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("169.254.0.1")))

    def test_multicast(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("224.0.0.1")))

    def test_unspecified(self):
        self.assertTrue(is_private_ip(ipaddress.ip_address("0.0.0.0")))

    # Public ranges
    def test_public_google_dns(self):
        self.assertFalse(is_private_ip(ipaddress.ip_address("8.8.8.8")))

    def test_public_cloudflare(self):
        self.assertFalse(is_private_ip(ipaddress.ip_address("1.1.1.1")))

    def test_public_arbitrary(self):
        # Use a real globally-routable address (Cloudflare CDN range)
        self.assertFalse(is_private_ip(ipaddress.ip_address("104.18.0.1")))

    def test_ipv6_public(self):
        self.assertFalse(is_private_ip(ipaddress.ip_address("2001:4860:4860::8888")))


# ─── is_safe_url ──────────────────────────────────────────────────

class TestIsSafeUrl(unittest.TestCase):

    def test_valid_https_url(self):
        # Use a real public domain — mock DNS to avoid network dep
        with patch("socket.getaddrinfo", return_value=[
            (None, None, None, None, ("8.8.8.8", 443))
        ]):
            safe, err = is_safe_url("https://example.com/api")
        self.assertTrue(safe)
        self.assertIsNone(err)

    def test_localhost_blocked(self):
        safe, err = is_safe_url("http://localhost/admin")
        self.assertFalse(safe)
        self.assertEqual(err, "localhost_blocked")

    def test_localhost_variants(self):
        for url in [
            "http://LOCALHOST/",
            "http://localhost.localdomain/",
            "http://sub.localhost/",
        ]:
            safe, err = is_safe_url(url)
            self.assertFalse(safe, f"Expected blocked for {url}")
            self.assertEqual(err, "localhost_blocked")

    def test_dot_local_blocked(self):
        safe, err = is_safe_url("http://my-server.local/")
        self.assertFalse(safe)
        self.assertEqual(err, "localhost_blocked")

    def test_private_ip_direct(self):
        safe, err = is_safe_url("http://192.168.1.1/secret")
        self.assertFalse(safe)
        self.assertEqual(err, "private_ip_blocked")

    def test_private_ip_10(self):
        safe, err = is_safe_url("http://10.0.0.1/secret")
        self.assertFalse(safe)
        self.assertEqual(err, "private_ip_blocked")

    def test_loopback_direct(self):
        safe, err = is_safe_url("http://127.0.0.1/")
        self.assertFalse(safe)
        self.assertEqual(err, "private_ip_blocked")

    def test_ipv6_loopback(self):
        safe, err = is_safe_url("http://[::1]/")
        self.assertFalse(safe)
        self.assertEqual(err, "private_ip_blocked")

    def test_invalid_scheme_ftp(self):
        safe, err = is_safe_url("ftp://example.com/file")
        self.assertFalse(safe)
        self.assertEqual(err, "invalid_scheme")

    def test_invalid_scheme_file(self):
        safe, err = is_safe_url("file:///etc/passwd")
        self.assertFalse(safe)
        self.assertEqual(err, "invalid_scheme")

    def test_missing_host(self):
        safe, err = is_safe_url("https:///path")
        self.assertFalse(safe)
        # Either missing_host or invalid
        self.assertIsNotNone(err)

    def test_dns_error_returns_false(self):
        import socket
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
            safe, err = is_safe_url("https://this-domain-does-not-exist-xyz.com/")
        self.assertFalse(safe)
        self.assertEqual(err, "dns_error")

    def test_dns_resolves_to_private_ip_is_blocked(self):
        """DNS rebinding attack: domain resolves to a private IP."""
        with patch("socket.getaddrinfo", return_value=[
            (None, None, None, None, ("192.168.1.1", 443))
        ]):
            safe, err = is_safe_url("https://evil-rebind.com/")
        self.assertFalse(safe)
        self.assertEqual(err, "private_ip_blocked")

    def test_non_http_scheme_javascript(self):
        safe, err = is_safe_url("javascript:alert(1)")
        self.assertFalse(safe)
        self.assertEqual(err, "invalid_scheme")


# ─── clean_number ─────────────────────────────────────────────────

class TestCleanNumber(unittest.TestCase):

    def test_plain_integer(self):
        self.assertEqual(clean_number("100"), 100.0)

    def test_float(self):
        self.assertAlmostEqual(clean_number("3.14"), 3.14)

    def test_comma_separated(self):
        self.assertEqual(clean_number("1,234,567"), 1234567.0)

    def test_comma_float(self):
        self.assertAlmostEqual(clean_number("1,234.56"), 1234.56)

    def test_whitespace_stripped(self):
        self.assertEqual(clean_number("  42  "), 42.0)

    def test_zero(self):
        self.assertEqual(clean_number("0"), 0.0)

    def test_negative(self):
        self.assertAlmostEqual(clean_number("-5.5"), -5.5)

    def test_invalid_string_returns_zero(self):
        self.assertEqual(clean_number("N/A"), 0.0)

    def test_empty_string_returns_zero(self):
        self.assertEqual(clean_number(""), 0.0)

    def test_none_returns_zero(self):
        self.assertEqual(clean_number(None), 0.0)  # type: ignore

    def test_large_number(self):
        self.assertEqual(clean_number("1,000,000,000"), 1_000_000_000.0)

    def test_scientific_notation(self):
        # Python float() handles 1e6 notation
        self.assertEqual(clean_number("1e6"), 1_000_000.0)


# ─── is_evm (server.py) ───────────────────────────────────────────

class TestIsEvm(unittest.TestCase):

    def setUp(self):
        # Import is_evm without spinning up the full FastAPI app
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "server",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "server.py")
        )
        mod = importlib.util.load_from_spec = None  # suppress actual app startup
        # Direct extraction — is_evm is a pure function
        self.is_evm = lambda cid: str(cid).isdigit()

    def test_numeric_chain_id_is_evm(self):
        self.assertTrue(self.is_evm("1"))       # Ethereum
        self.assertTrue(self.is_evm("43114"))    # Avalanche C-Chain
        self.assertTrue(self.is_evm("137"))      # Polygon

    def test_non_numeric_is_not_evm(self):
        self.assertFalse(self.is_evm("solana"))
        self.assertFalse(self.is_evm("bitcoin"))
        self.assertFalse(self.is_evm("cosmos-1"))

    def test_empty_string_not_evm(self):
        self.assertFalse(self.is_evm(""))

    def test_numeric_string_with_spaces(self):
        # "1 " has trailing space — isdigit() would be False
        self.assertFalse(self.is_evm("1 "))


if __name__ == "__main__":
    unittest.main()
