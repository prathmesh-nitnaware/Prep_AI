"""
test_step2b1_ip_rate_limiter.py — Tests for Step 2B.1 Client IP Resolution & Rate Limiter
========================================================================================
Covers:
1. Proxy strategy parsing and validation ('direct', 'nginx', 'render', and invalid fallback).
2. Client IP resolution across all three modes:
   - Direct mode: ignores all forwarded headers; uses socket remote_addr.
   - Nginx mode: trusts only validated X-Real-IP; ignores CF-Connecting-IP and X-Forwarded-For.
   - Render mode: trusts only validated CF-Connecting-IP; ignores X-Real-IP and X-Forwarded-For.
3. Strict rejection of forged X-Forwarded-For across every mode.
4. Validation of IPv4 and IPv6 formats.
5. Rejection of malformed, empty, and comma-separated proxy headers.
6. Fallback to remote_addr with warning logging that never discloses raw untrusted header contents.
7. Consistent client IP resolution between rate limiting and request logging.
8. HTTP 429 response structure, retry headers, and threshold behavior.
9. Token-bucket arithmetic, refill calculations, and process-local isolation.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Add backend directory and virtualenv site-packages to sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE_PACKAGES = os.path.join(BACKEND_DIR, ".venv", "Lib", "site-packages")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if os.path.exists(SITE_PACKAGES) and SITE_PACKAGES not in sys.path:
    sys.path.append(SITE_PACKAGES)

# Mock external dependencies that may not be installed on host
for mod in ["flask_cors", "app.controllers.interview_socket", "routes", "extensions", "psycopg2"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Ensure minimal Flask-like environment for request mocking
from config import Config, parse_proxy_strategy
from utils.middleware import resolve_client_ip, rate_limit
from utils.rate_limiter import InMemoryRateLimiterBackend


class MockRequest:
    """Mock Flask request object for testing header extraction."""
    def __init__(self, remote_addr="127.0.0.1", headers=None, path="/api/test", method="GET"):
        self.remote_addr = remote_addr
        self.headers = headers or {}
        self.path = path
        self.method = method


class TestProxyStrategyParsing(unittest.TestCase):
    """Test validation and normalization of PROXY_STRATEGY."""

    def test_valid_strategies(self):
        self.assertEqual(parse_proxy_strategy("direct"), "direct")
        self.assertEqual(parse_proxy_strategy("DIRECT"), "direct")
        self.assertEqual(parse_proxy_strategy("  direct  "), "direct")
        self.assertEqual(parse_proxy_strategy("nginx"), "nginx")
        self.assertEqual(parse_proxy_strategy("  NGINX  "), "nginx")
        self.assertEqual(parse_proxy_strategy("render"), "render")
        self.assertEqual(parse_proxy_strategy("  RENDER  "), "render")

    def test_invalid_strategies_fall_back_to_direct_with_warning(self):
        invalid_values = ["aws", "cloudflare", "custom", "", "   ", "maybe", 12345]
        for val in invalid_values:
            with self.subTest(val=val):
                with patch("logging.getLogger") as mock_get_logger:
                    mock_logger = MagicMock()
                    mock_get_logger.return_value = mock_logger

                    result = parse_proxy_strategy(val)
                    self.assertEqual(result, "direct")
                    mock_logger.warning.assert_called_once()
                    warning_msg = mock_logger.warning.call_args[0][0]
                    self.assertIn("Invalid PROXY_STRATEGY", warning_msg)

    def test_none_defaults_to_direct_without_warning(self):
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            result = parse_proxy_strategy(None)
            self.assertEqual(result, "direct")
            mock_logger.warning.assert_not_called()


class TestClientIPResolution(unittest.TestCase):
    """Test resolve_client_ip across all strategies, headers, and validation cases."""

    # ------------------ DIRECT MODE ------------------
    def test_direct_mode_uses_remote_addr(self):
        req = MockRequest(remote_addr="198.51.100.1")
        with patch.object(Config, "PROXY_STRATEGY", "direct"):
            self.assertEqual(resolve_client_ip(req), "198.51.100.1")

    def test_direct_mode_ignores_all_forwarded_headers(self):
        req = MockRequest(
            remote_addr="198.51.100.1",
            headers={
                "X-Real-IP": "203.0.113.10",
                "CF-Connecting-IP": "203.0.113.20",
                "X-Forwarded-For": "203.0.113.30, 10.0.0.1",
            }
        )
        with patch.object(Config, "PROXY_STRATEGY", "direct"):
            self.assertEqual(resolve_client_ip(req), "198.51.100.1")

    # ------------------ NGINX MODE ------------------
    def test_nginx_mode_trusts_valid_x_real_ip(self):
        req = MockRequest(
            remote_addr="172.18.0.2",
            headers={"X-Real-IP": "203.0.113.55"}
        )
        with patch.object(Config, "PROXY_STRATEGY", "nginx"):
            self.assertEqual(resolve_client_ip(req), "203.0.113.55")

    def test_nginx_mode_ignores_forged_cf_and_xff(self):
        req = MockRequest(
            remote_addr="172.18.0.2",
            headers={
                "X-Real-IP": "203.0.113.55",
                "CF-Connecting-IP": "1.2.3.4",
                "X-Forwarded-For": "5.6.7.8, 9.10.11.12",
            }
        )
        with patch.object(Config, "PROXY_STRATEGY", "nginx"):
            self.assertEqual(resolve_client_ip(req), "203.0.113.55")

    def test_nginx_mode_falls_back_when_x_real_ip_missing(self):
        req = MockRequest(remote_addr="172.18.0.2", headers={})
        with patch.object(Config, "PROXY_STRATEGY", "nginx"), \
             patch("utils.middleware.logger.warning") as mock_warn:
            self.assertEqual(resolve_client_ip(req), "172.18.0.2")
            mock_warn.assert_called_once()
            self.assertIn("missing", mock_warn.call_args[0][0])

    def test_nginx_mode_falls_back_when_x_real_ip_malformed(self):
        req = MockRequest(
            remote_addr="172.18.0.2",
            headers={"X-Real-IP": "invalid_ip_format"}
        )
        with patch.object(Config, "PROXY_STRATEGY", "nginx"), \
             patch("utils.middleware.logger.warning") as mock_warn:
            self.assertEqual(resolve_client_ip(req), "172.18.0.2")
            mock_warn.assert_called_once()
            self.assertIn("malformed", mock_warn.call_args[0][0])

    def test_nginx_mode_rejects_comma_separated_chain(self):
        req = MockRequest(
            remote_addr="172.18.0.2",
            headers={"X-Real-IP": "203.0.113.55, 10.0.0.1"}
        )
        with patch.object(Config, "PROXY_STRATEGY", "nginx"), \
             patch("utils.middleware.logger.warning") as mock_warn:
            self.assertEqual(resolve_client_ip(req), "172.18.0.2")
            mock_warn.assert_called_once()
            self.assertIn("comma-separated", mock_warn.call_args[0][0])

    # ------------------ RENDER MODE ------------------
    def test_render_mode_trusts_valid_cf_connecting_ip(self):
        req = MockRequest(
            remote_addr="10.0.4.15",
            headers={"CF-Connecting-IP": "198.51.100.99"}
        )
        with patch.object(Config, "PROXY_STRATEGY", "render"):
            self.assertEqual(resolve_client_ip(req), "198.51.100.99")

    def test_render_mode_ignores_forged_x_real_ip_and_xff(self):
        req = MockRequest(
            remote_addr="10.0.4.15",
            headers={
                "CF-Connecting-IP": "198.51.100.99",
                "X-Real-IP": "1.2.3.4",
                "X-Forwarded-For": "5.6.7.8, 9.10.11.12",
            }
        )
        with patch.object(Config, "PROXY_STRATEGY", "render"):
            self.assertEqual(resolve_client_ip(req), "198.51.100.99")

    def test_render_mode_falls_back_when_cf_connecting_ip_missing(self):
        req = MockRequest(remote_addr="10.0.4.15", headers={})
        with patch.object(Config, "PROXY_STRATEGY", "render"), \
             patch("utils.middleware.logger.warning") as mock_warn:
            self.assertEqual(resolve_client_ip(req), "10.0.4.15")
            mock_warn.assert_called_once()
            self.assertIn("missing", mock_warn.call_args[0][0])

    def test_render_mode_falls_back_when_cf_connecting_ip_malformed(self):
        req = MockRequest(
            remote_addr="10.0.4.15",
            headers={"CF-Connecting-IP": "not_an_ip"}
        )
        with patch.object(Config, "PROXY_STRATEGY", "render"), \
             patch("utils.middleware.logger.warning") as mock_warn:
            self.assertEqual(resolve_client_ip(req), "10.0.4.15")
            mock_warn.assert_called_once()
            self.assertIn("malformed", mock_warn.call_args[0][0])

    def test_render_mode_rejects_comma_separated_chain(self):
        req = MockRequest(
            remote_addr="10.0.4.15",
            headers={"CF-Connecting-IP": "198.51.100.99, 10.0.0.1"}
        )
        with patch.object(Config, "PROXY_STRATEGY", "render"), \
             patch("utils.middleware.logger.warning") as mock_warn:
            self.assertEqual(resolve_client_ip(req), "10.0.4.15")
            mock_warn.assert_called_once()
            self.assertIn("comma-separated", mock_warn.call_args[0][0])

    # ------------------ IP SYNTAX & SECURITY ------------------
    def test_ipv4_and_ipv6_validation(self):
        ipv4_cases = ["1.1.1.1", "192.168.1.1", "203.0.113.250"]
        ipv6_cases = ["2001:db8::1", "::1", "fe80::1ff:fe23:4567:890a"]

        with patch.object(Config, "PROXY_STRATEGY", "nginx"):
            for ip in ipv4_cases + ipv6_cases:
                with self.subTest(ip=ip):
                    req = MockRequest(headers={"X-Real-IP": ip})
                    self.assertEqual(resolve_client_ip(req), ip)

    def test_security_warning_does_not_leak_untrusted_header_value(self):
        malicious_payload = "<script>alert('injection')</script>; DROP TABLE users;"
        req = MockRequest(
            remote_addr="127.0.0.1",
            headers={"X-Real-IP": malicious_payload}
        )
        with patch.object(Config, "PROXY_STRATEGY", "nginx"), \
             patch("utils.middleware.logger.warning") as mock_warn:
            resolve_client_ip(req)
            mock_warn.assert_called_once()
            # Ensure the raw malicious string never appears in log message or extra dict
            warning_msg = mock_warn.call_args[0][0]
            extra_dict = mock_warn.call_args[1].get("extra", {})
            self.assertNotIn(malicious_payload, warning_msg)
            self.assertNotIn(malicious_payload, str(extra_dict))


class TestRateLimiterArithmeticAndIsolation(unittest.TestCase):
    """Test token bucket math, refill calculation, and process-local isolation."""

    def test_token_bucket_initialization(self):
        limiter = InMemoryRateLimiterBackend(capacity=60, refill_rate=15.0)
        bucket = limiter._new_bucket()
        self.assertEqual(bucket["tokens"], 60.0)
        self.assertAlmostEqual(bucket["last_refill"], time.monotonic(), delta=1.0)

    def test_token_consumption_and_refill_per_second(self):
        limiter = InMemoryRateLimiterBackend(capacity=60, refill_rate=15.0)
        ip = "192.0.2.1"

        # Drain 10 tokens
        for _ in range(10):
            self.assertTrue(limiter.is_allowed(ip))
        self.assertEqual(limiter.remaining(ip), 50)

        # Simulate 1 second elapsed -> refill 15 tokens
        bucket = limiter._buckets[ip]
        bucket["last_refill"] -= 1.0  # 1.0 second in the past
        limiter._refill(bucket)

        # 50 + 15 = 65, capped at capacity 60
        self.assertEqual(bucket["tokens"], 60.0)

    def test_refill_rate_calculation_is_tokens_per_second(self):
        limiter = InMemoryRateLimiterBackend(capacity=60, refill_rate=15.0)
        ip = "192.0.2.2"

        # Fully drain bucket
        for _ in range(60):
            self.assertTrue(limiter.is_allowed(ip))
        self.assertFalse(limiter.is_allowed(ip))
        self.assertEqual(limiter.remaining(ip), 0)

        # Advance time by 0.2 seconds (should refill exactly 0.2 * 15 = 3.0 tokens)
        bucket = limiter._buckets[ip]
        bucket["last_refill"] -= 0.2
        limiter._refill(bucket)
        self.assertAlmostEqual(bucket["tokens"], 3.0, delta=0.1)

    def test_process_local_isolation(self):
        """Two separate limiter instances (modeling independent Gunicorn workers) have isolated buckets."""
        worker1 = InMemoryRateLimiterBackend(capacity=60, refill_rate=15.0)
        worker2 = InMemoryRateLimiterBackend(capacity=60, refill_rate=15.0)
        ip = "198.51.100.5"

        # Drain worker 1 completely
        for _ in range(60):
            worker1.is_allowed(ip)
        self.assertFalse(worker1.is_allowed(ip))

        # Worker 2 must remain completely full
        self.assertEqual(worker2.remaining(ip), 60)
        self.assertTrue(worker2.is_allowed(ip))

    def test_shared_fallback_ip_shares_rate_limit_bucket(self):
        """When multiple clients fall back to the same IP (e.g. 127.0.0.1), they consume the same bucket."""
        limiter = InMemoryRateLimiterBackend(capacity=60, refill_rate=15.0)
        fallback_ip = "127.0.0.1"

        # Client A consumes 40 tokens
        for _ in range(40):
            limiter.is_allowed(fallback_ip)
        self.assertEqual(limiter.remaining(fallback_ip), 20)

        # Client B connecting via same fallback IP has only 20 remaining
        self.assertEqual(limiter.remaining(fallback_ip), 20)


class TestRateLimitDecoratorIntegration(unittest.TestCase):
    """Test rate_limit decorator behavior, 429 response, and logger consistency."""

    def test_rate_limit_decorator_429_response_and_headers(self):
        from flask import Flask
        app = Flask(__name__)

        # Dedicated limiter with capacity=2 to test threshold quickly
        test_limiter = InMemoryRateLimiterBackend(capacity=2, refill_rate=0.0)

        with patch("utils.middleware._rate_limiter", test_limiter), \
             patch.object(Config, "PROXY_STRATEGY", "direct"):

            @app.route("/test-endpoint")
            @rate_limit
            def sample_route():
                return {"status": "ok"}, 200

            client = app.test_client()

            # Request 1: Allowed
            resp1 = client.get("/test-endpoint", environ_base={"REMOTE_ADDR": "203.0.113.88"})
            self.assertEqual(resp1.status_code, 200)

            # Request 2: Allowed
            resp2 = client.get("/test-endpoint", environ_base={"REMOTE_ADDR": "203.0.113.88"})
            self.assertEqual(resp2.status_code, 200)

            # Request 3: Throttled (429)
            resp3 = client.get("/test-endpoint", environ_base={"REMOTE_ADDR": "203.0.113.88"})
            self.assertEqual(resp3.status_code, 429)

            data = resp3.get_json()
            self.assertEqual(data["error"], "Too many requests. Please slow down.")
            self.assertEqual(data["retry_after_seconds"], 5)
            self.assertEqual(resp3.headers.get("Retry-After"), "5")
            self.assertEqual(resp3.headers.get("X-RateLimit-Remaining"), "0")

    def test_consistent_ip_resolution_in_request_logger(self):
        """Verify register_request_logger uses the exact same resolve_client_ip logic."""
        from flask import Flask
        from utils.middleware import register_request_logger

        app = Flask(__name__)
        register_request_logger(app)

        @app.route("/audit-endpoint")
        def audit_route():
            return {"status": "audited"}, 200

        with patch.object(Config, "PROXY_STRATEGY", "nginx"), \
             patch("utils.middleware.logger.info") as mock_info:

            client = app.test_client()
            client.get(
                "/audit-endpoint",
                headers={
                    "X-Real-IP": "203.0.113.99",
                    "X-Forwarded-For": "spoofed.ip.address",
                },
                environ_base={"REMOTE_ADDR": "172.18.0.2"}
            )

            mock_info.assert_called_once()
            extra = mock_info.call_args[1].get("extra", {})
            self.assertEqual(extra.get("ip"), "203.0.113.99")
            self.assertNotEqual(extra.get("ip"), "spoofed.ip.address")


if __name__ == "__main__":
    unittest.main()

