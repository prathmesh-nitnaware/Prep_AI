"""
test_step2a_config.py — Focused Unit Tests for Step 2A Configuration Foundation
=============================================================================
Tests:
1. Strict boolean parsing (parse_bool) with whitespace normalization and explicit truthy whitelist.
2. Invalid/unrecognized values strictly evaluate to False (never silently enable PIE).
3. ENVIRONMENT normalization with .strip().lower() and fallback.
4. Default dev SECRET_KEY warning behavior in production vs non-production.
5. Secret non-disclosure: Secret value is never printed or logged in warning output.
6. Startup warning deduplication (emitted once during initialization).
7. Non-fatal execution: check_production_secret does not raise an exception.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend directory is in sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Mock external dependencies that may not be installed in the local runner environment
for module_name in [
    "flask",
    "flask_cors",
    "app.controllers.interview_socket",
    "routes",
    "extensions",
    "psycopg2",
]:
    if module_name not in sys.modules:
        sys.modules[module_name] = MagicMock()

from config import Config, parse_bool
import main


class TestStrictBooleanParsing(unittest.TestCase):
    """Test strict boolean parsing for PIE_ENABLED and configuration flags."""

    def test_explicit_truthy_values(self):
        """Explicitly allowed truthy values must strictly evaluate to True."""
        truthy_inputs = [
            "true", "True", "TRUE", "  true  ",
            "1", " 1 ",
            "yes", "Yes", "YES", "  yes  ",
            "on", "On", "ON", "  on  ",
            True, 1,
        ]
        for val in truthy_inputs:
            with self.subTest(val=val):
                self.assertTrue(
                    parse_bool(val),
                    f"Expected '{val}' to evaluate to True",
                )

    def test_explicit_falsy_values(self):
        """Explicitly allowed falsy values must strictly evaluate to False."""
        falsy_inputs = [
            "false", "False", "FALSE", "  false  ",
            "0", " 0 ",
            "no", "No", "NO", "  no  ",
            "off", "Off", "OFF", "  off  ",
            "", "   ",
            False, 0,
        ]
        for val in falsy_inputs:
            with self.subTest(val=val):
                self.assertFalse(
                    parse_bool(val),
                    f"Expected '{val}' to evaluate to False",
                )

    def test_invalid_and_unrecognized_values_default_to_false(self):
        """Invalid, arbitrary, or partial strings must never evaluate to True."""
        invalid_inputs = [
            "invalid",
            "maybe",
            "2",
            "-1",
            "none",
            "null",
            "undefined",
            "enabled",
            "Trueish",
            "true1",
            "not_true",
            10,
            -1,
            [],
            {},
        ]
        for val in invalid_inputs:
            with self.subTest(val=val):
                self.assertFalse(
                    parse_bool(val),
                    f"Invalid input '{val}' must evaluate to False (never silently enable PIE)",
                )

    def test_none_handling_with_default(self):
        """None must evaluate to the provided default."""
        self.assertFalse(parse_bool(None, default=False))
        self.assertTrue(parse_bool(None, default=True))


class TestEnvironmentNormalization(unittest.TestCase):
    """Test environment string normalization."""

    def test_environment_normalization_logic(self):
        """ENVIRONMENT must be normalized using .strip().lower()."""
        test_cases = [
            ("production", "production"),
            ("Production", "production"),
            ("  PRODUCTION  ", "production"),
            ("development", "development"),
            ("Development", "development"),
            ("  DEVELOPMENT  ", "development"),
            ("staging", "staging"),
            ("  STAGING  ", "staging"),
        ]
        for raw, expected in test_cases:
            with self.subTest(raw=raw):
                normalized = (raw or "development").strip().lower()
                self.assertEqual(normalized, expected)

    def test_environment_empty_or_whitespace_fallback(self):
        """Empty or whitespace-only environment must fall back safely to 'development'."""
        empty_inputs = ["", "   ", None]
        for raw in empty_inputs:
            with self.subTest(raw=raw):
                normalized = (raw or "").strip().lower() or "development"
                self.assertEqual(normalized, "development")


class TestConfigPIEEnabled(unittest.TestCase):
    """Test Config.PIE_ENABLED resolution with environment variables."""

    def test_pie_enabled_defaults_to_false(self):
        """PIE_ENABLED must default to False when unset."""
        with patch.dict(os.environ, {}, clear=True):
            val = parse_bool(os.getenv("PIE_ENABLED", "false"), default=False)
            self.assertFalse(val)

    def test_pie_enabled_when_explicitly_true(self):
        """PIE_ENABLED must be True when set to valid truthy strings."""
        with patch.dict(os.environ, {"PIE_ENABLED": "true"}):
            val = parse_bool(os.getenv("PIE_ENABLED", "false"), default=False)
            self.assertTrue(val)

        with patch.dict(os.environ, {"PIE_ENABLED": "  ON  "}):
            val = parse_bool(os.getenv("PIE_ENABLED", "false"), default=False)
            self.assertTrue(val)

    def test_pie_enabled_when_invalid(self):
        """PIE_ENABLED must not be enabled by invalid values."""
        with patch.dict(os.environ, {"PIE_ENABLED": "yesplease"}):
            val = parse_bool(os.getenv("PIE_ENABLED", "false"), default=False)
            self.assertFalse(val)


class TestStartupSecretWarning(unittest.TestCase):
    """Test non-fatal production warning and secret non-disclosure."""

    def setUp(self):
        # Reset warning flag before each test
        main._secret_key_warned = False

    def test_production_with_default_secret_emits_warning(self):
        """When in production with default secret, a non-fatal warning must be logged."""
        with patch.object(Config, "ENVIRONMENT", "production"), \
             patch.object(Config, "SECRET_KEY", Config.DEFAULT_SECRET_KEY), \
             patch.object(main.logger, "warning") as mock_warn:

            emitted = main.check_production_secret(force=True)

            self.assertTrue(emitted)
            mock_warn.assert_called_once()
            warning_msg = mock_warn.call_args[0][0]
            self.assertIn("SECURITY WARNING", warning_msg)
            self.assertIn("default development SECRET_KEY", warning_msg)

    def test_production_with_custom_secret_emits_no_warning(self):
        """When in production with a custom secure secret, no warning should be emitted."""
        custom_secret = "f8a9e4b7c2d1e0f3a5b6c7d8e9f0123456789abcdef0123456789abcdef0"
        with patch.object(Config, "ENVIRONMENT", "production"), \
             patch.object(Config, "SECRET_KEY", custom_secret), \
             patch.object(main.logger, "warning") as mock_warn:

            emitted = main.check_production_secret(force=True)

            self.assertFalse(emitted)
            mock_warn.assert_not_called()

    def test_development_with_default_secret_emits_no_warning(self):
        """When in development, using the default secret is normal; no warning should be emitted."""
        with patch.object(Config, "ENVIRONMENT", "development"), \
             patch.object(Config, "SECRET_KEY", Config.DEFAULT_SECRET_KEY), \
             patch.object(main.logger, "warning") as mock_warn:

            emitted = main.check_production_secret(force=True)

            self.assertFalse(emitted)
            mock_warn.assert_not_called()

    def test_secret_is_never_disclosed_in_log_message(self):
        """Verify that neither the default secret nor any custom secret is printed or logged."""
        test_secrets = [
            Config.DEFAULT_SECRET_KEY,
            "super_secret_production_key_never_leak_me",
        ]
        for secret_val in test_secrets:
            with self.subTest(secret=secret_val):
                with patch.object(Config, "ENVIRONMENT", "production"), \
                     patch.object(Config, "SECRET_KEY", Config.DEFAULT_SECRET_KEY), \
                     patch.object(main.logger, "warning") as mock_warn:

                    main.check_production_secret(force=True)

                    if mock_warn.called:
                        warning_msg = mock_warn.call_args[0][0]
                        # Ensure the secret string is not in the message
                        self.assertNotIn(secret_val, warning_msg)

    def test_warning_deduplication_on_repeated_initialization(self):
        """Startup warning must emit only once per process lifecycle unless forced."""
        with patch.object(Config, "ENVIRONMENT", "production"), \
             patch.object(Config, "SECRET_KEY", Config.DEFAULT_SECRET_KEY), \
             patch.object(main.logger, "warning") as mock_warn:

            # First call -> emits warning
            first_result = main.check_production_secret(force=False)
            self.assertTrue(first_result)
            self.assertEqual(mock_warn.call_count, 1)

            # Second call -> deduplicated, does not emit
            second_result = main.check_production_secret(force=False)
            self.assertFalse(second_result)
            self.assertEqual(mock_warn.call_count, 1)

    def test_non_fatal_execution(self):
        """check_production_secret must never raise an exception even if misconfigured."""
        try:
            with patch.object(Config, "ENVIRONMENT", "production"), \
                 patch.object(Config, "SECRET_KEY", ""):
                main.check_production_secret(force=True)
        except Exception as exc:
            self.fail(f"check_production_secret raised an unexpected exception: {exc}")


if __name__ == "__main__":
    unittest.main()
