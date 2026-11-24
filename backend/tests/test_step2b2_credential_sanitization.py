"""
test_step2b2_credential_sanitization.py — Tests for Step 2B.2 Credential Sanitization
====================================================================================
Covers:
1. JudgeService credential resolution and priority:
   - Missing credentials.
   - Empty credentials.
   - Whitespace-only credentials.
   - Placeholder credentials ('REPLACE_WITH_YOUR_KEY').
   - RAPIDAPI_KEY takes priority over JUDGE0_API_KEY.
   - JUDGE0_API_KEY fallback when RAPIDAPI_KEY is missing/empty/whitespace/placeholder.
2. Fail-closed behavior:
   - Zero outbound HTTP network requests when unconfigured.
   - Exact error contract: {"error": "Code execution engine is not configured."}.
3. Valid execution contract (mocked):
   - Correct X-RapidAPI-Key header injection.
   - Response contract verification on HTTP 201.
   - Error handling on non-201 response.
4. Credential non-disclosure:
   - API keys and tokens never appear in log output.
5. setup_admin safety:
   - Terminates safely with sys.exit(1) and error diagnostic.
   - Performs zero database connections or writes.
6. migrate_admin safety:
   - Safely aborts before any DB operations if CONFIRM_ADMIN_MIGRATION != 'true'.
   - Safely aborts if MONGO_URI is missing or empty.
   - Zero import-time database side effects (extensions not imported on module import).
   - Zero database connections or client creation in either abort case.
   - Contains zero plaintext password output in source or execution.
"""

import os
import sys
import io
import subprocess
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend directory is in sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.judge_service import JudgeService
import scripts.setup_admin as setup_admin_module
import db.migrate_admin as migrate_admin_module


class TestJudgeServiceCredentialResolution(unittest.TestCase):
    """Test dynamic credential resolution and priority in JudgeService."""

    def test_missing_credentials_returns_empty_string(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(JudgeService.get_api_key(), "")

    def test_empty_and_whitespace_only_credentials_return_empty_string(self):
        whitespace_cases = [
            {"RAPIDAPI_KEY": ""},
            {"RAPIDAPI_KEY": "   "},
            {"JUDGE0_API_KEY": ""},
            {"JUDGE0_API_KEY": "   "},
            {"RAPIDAPI_KEY": "   ", "JUDGE0_API_KEY": "   "},
        ]
        for env_dict in whitespace_cases:
            with self.subTest(env=env_dict):
                with patch.dict(os.environ, env_dict, clear=True):
                    self.assertEqual(JudgeService.get_api_key(), "")

    def test_placeholder_credentials_return_empty_string(self):
        with patch.dict(os.environ, {"RAPIDAPI_KEY": "REPLACE_WITH_YOUR_KEY"}, clear=True):
            self.assertEqual(JudgeService.get_api_key(), "")

        with patch.dict(os.environ, {"JUDGE0_API_KEY": "REPLACE_WITH_YOUR_KEY"}, clear=True):
            self.assertEqual(JudgeService.get_api_key(), "")

    def test_rapidapi_key_takes_priority_over_judge0_api_key(self):
        env_dict = {
            "RAPIDAPI_KEY": "priority_rapidapi_key_123",
            "JUDGE0_API_KEY": "secondary_judge0_key_456",
        }
        with patch.dict(os.environ, env_dict, clear=True):
            self.assertEqual(JudgeService.get_api_key(), "priority_rapidapi_key_123")

    def test_judge0_api_key_fallback_when_rapidapi_is_missing(self):
        env_dict = {
            "JUDGE0_API_KEY": "fallback_judge0_key_456",
        }
        with patch.dict(os.environ, env_dict, clear=True):
            self.assertEqual(JudgeService.get_api_key(), "fallback_judge0_key_456")

    def test_whitespace_rapidapi_key_falls_back_to_valid_judge0_api_key(self):
        env_dict = {
            "RAPIDAPI_KEY": "   ",
            "JUDGE0_API_KEY": "valid_judge0_key_789",
        }
        with patch.dict(os.environ, env_dict, clear=True):
            self.assertEqual(JudgeService.get_api_key(), "valid_judge0_key_789")

    def test_placeholder_rapidapi_key_falls_back_to_valid_judge0_api_key(self):
        env_dict = {
            "RAPIDAPI_KEY": "REPLACE_WITH_YOUR_KEY",
            "JUDGE0_API_KEY": "valid_judge0_key_789",
        }
        with patch.dict(os.environ, env_dict, clear=True):
            self.assertEqual(JudgeService.get_api_key(), "valid_judge0_key_789")


class TestJudgeServiceFailClosedBehavior(unittest.TestCase):
    """Test that JudgeService strictly fails closed without making network requests."""

    @patch("requests.post")
    def test_unconfigured_key_fails_closed_without_http_request(self, mock_post):
        with patch.dict(os.environ, {}, clear=True):
            result = JudgeService.execute(code="print('hello')", language="python")
            self.assertEqual(result, {"error": "Code execution engine is not configured."})
            mock_post.assert_not_called()

    @patch("requests.post")
    def test_placeholder_key_fails_closed_without_http_request(self, mock_post):
        with patch.dict(os.environ, {"RAPIDAPI_KEY": "REPLACE_WITH_YOUR_KEY"}, clear=True):
            result = JudgeService.execute(code="print('hello')", language="python")
            self.assertEqual(result, {"error": "Code execution engine is not configured."})
            mock_post.assert_not_called()

    @patch("requests.post")
    def test_whitespace_key_fails_closed_without_http_request(self, mock_post):
        with patch.dict(os.environ, {"RAPIDAPI_KEY": "   \t  "}, clear=True):
            result = JudgeService.execute(code="print('hello')", language="python")
            self.assertEqual(result, {"error": "Code execution engine is not configured."})
            mock_post.assert_not_called()

    def test_fail_closed_warning_does_not_leak_keys(self):
        test_secret = "leaked_secret_should_never_appear"
        with patch.dict(os.environ, {"RAPIDAPI_KEY": "REPLACE_WITH_YOUR_KEY"}, clear=True), \
             patch("app.services.judge_service.logger.warning") as mock_warn:

            JudgeService.execute(code="print('hello')", language="python")
            mock_warn.assert_called_once()
            warning_msg = mock_warn.call_args[0][0]
            self.assertIn("not configured", warning_msg)
            self.assertNotIn(test_secret, warning_msg)
            self.assertNotIn("REPLACE_WITH_YOUR_KEY", warning_msg)


class TestJudgeServiceExecutionContract(unittest.TestCase):
    """Test valid execution behavior and response contract preservation (mocked HTTP)."""

    @patch("requests.post")
    def test_valid_key_dispatches_http_with_correct_headers(self, mock_post):
        import base64

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "stdout": base64.b64encode(b"Hello World\n").decode(),
            "stderr": "",
            "compile_output": "",
            "time": "0.02",
            "memory": 1240,
            "status": {"description": "Accepted"},
        }
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"RAPIDAPI_KEY": "valid_rapidapi_key_xyz"}, clear=True):
            result = JudgeService.execute(code="print('Hello World')", language="python", stdin="test_input")

            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            headers = call_kwargs.get("headers", {})

            # Header verification
            self.assertEqual(headers.get("X-RapidAPI-Key"), "valid_rapidapi_key_xyz")
            self.assertEqual(headers.get("X-RapidAPI-Host"), "judge0-ce.p.rapidapi.com")

            # Contract verification
            self.assertEqual(result["stdout"], "Hello World\n")
            self.assertEqual(result["status"], "Accepted")
            self.assertEqual(result["time"], "0.02")
            self.assertEqual(result["memory"], 1240)

    @patch("requests.post")
    def test_valid_key_handles_non_201_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"RAPIDAPI_KEY": "valid_key"}, clear=True):
            result = JudgeService.execute(code="invalid syntax", language="python")
            self.assertEqual(result, {"error": "Submission failed"})


class TestSetupAdminDisarmed(unittest.TestCase):
    """Test that setup_admin.py is completely disarmed and refuses execution."""

    def test_setup_admin_exits_with_code_1_and_diagnostic(self):
        output_buffer = io.StringIO()
        with patch("sys.stdout", output_buffer), patch("sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit(1)

            with self.assertRaises(SystemExit) as cm:
                setup_admin_module.setup_admin()

            self.assertEqual(cm.exception.code, 1)
            output = output_buffer.getvalue()
            self.assertIn("obsolete and has been disarmed", output)
            self.assertIn("No database connections", output)

    def test_setup_admin_source_contains_no_hardcoded_credentials(self):
        setup_admin_path = os.path.join(BACKEND_DIR, "scripts", "setup_admin.py")
        with open(setup_admin_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Verify default email and password are gone
        self.assertNotIn("admin@gmail.com", content)
        self.assertNotIn("admin123", content)
        self.assertNotIn("users_collection", content)


class TestMigrateAdminGuarded(unittest.TestCase):
    """Test that migrate_admin.py is safely guarded against accidental execution."""

    def test_migrate_admin_aborts_without_confirmation_flag(self):
        output_buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), \
             patch.dict(sys.modules), \
             patch("sys.stdout", output_buffer):

            sys.modules.pop("extensions", None)
            sys.modules.pop("pymongo", None)
            migrate_admin_module.migrate_admin()

            output = output_buffer.getvalue()
            self.assertIn("[ABORTED]", output)
            self.assertIn("CONFIRM_ADMIN_MIGRATION=true", output)
            # Ensure extensions and pymongo were never loaded into sys.modules
            self.assertNotIn("extensions", sys.modules)
            self.assertNotIn("pymongo", sys.modules)

    def test_migrate_admin_aborts_when_confirmation_flag_is_false(self):
        output_buffer = io.StringIO()
        with patch.dict(os.environ, {"CONFIRM_ADMIN_MIGRATION": "false"}, clear=True), \
             patch.dict(sys.modules), \
             patch("sys.stdout", output_buffer):

            sys.modules.pop("extensions", None)
            sys.modules.pop("pymongo", None)
            migrate_admin_module.migrate_admin()

            output = output_buffer.getvalue()
            self.assertIn("[ABORTED]", output)
            self.assertNotIn("extensions", sys.modules)
            self.assertNotIn("pymongo", sys.modules)

    def test_migrate_admin_aborts_when_mongo_uri_is_missing(self):
        output_buffer = io.StringIO()
        # Save module-level MONGO_URI
        orig_mongo_uri = migrate_admin_module.MONGO_URI
        try:
            migrate_admin_module.MONGO_URI = ""
            with patch.dict(os.environ, {"CONFIRM_ADMIN_MIGRATION": "true"}, clear=True), \
                 patch.dict(sys.modules), \
                 patch("sys.stdout", output_buffer):

                sys.modules.pop("extensions", None)
                sys.modules.pop("pymongo", None)
                migrate_admin_module.migrate_admin()

                output = output_buffer.getvalue()
                self.assertIn("[ERROR] MONGO_URI environment variable is required", output)
                self.assertNotIn("extensions", sys.modules)
                self.assertNotIn("pymongo", sys.modules)
        finally:
            migrate_admin_module.MONGO_URI = orig_mongo_uri

    def test_migrate_admin_source_contains_no_plaintext_passwords(self):
        migrate_admin_path = os.path.join(BACKEND_DIR, "db", "migrate_admin.py")
        with open(migrate_admin_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Verify plaintext password print statement is completely removed
        self.assertNotIn("Password: admin123", content)
        self.assertNotIn("admin123", content)

    def test_migrate_admin_executes_when_confirmed_and_configured_with_mocks(self):
        mock_ext = MagicMock()
        mock_mongo = MagicMock()
        mock_cert = MagicMock()

        # Set up mock mongo document
        mock_client = mock_mongo.MongoClient.return_value
        mock_client["prepai"]["users"].find_one.return_value = {
            "name": "Admin",
            "email": "admin@prepai.test",
            "password": "hashed_admin_password",
        }
        mock_cur = mock_ext.get_db.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = [42]

        output_buffer = io.StringIO()
        with patch.dict(os.environ, {"CONFIRM_ADMIN_MIGRATION": "true", "MONGO_URI": "mongodb://mock:27017"}, clear=True), \
             patch.dict(sys.modules, {"extensions": mock_ext, "pymongo": mock_mongo, "certifi": mock_cert}), \
             patch("sys.stdout", output_buffer):

            migrate_admin_module.migrate_admin()

            output = output_buffer.getvalue()
            # Verified execution
            self.assertIn("[*] Initializing Neon DB schema...", output)
            self.assertIn("[DONE] Admin migrated successfully! Neon ID: 42", output)
            self.assertIn("Email:    admin@prepai.test", output)
            self.assertNotIn("Password", output)
            self.assertNotIn("admin123", output)

            # Verified database calls
            mock_ext.init_db.assert_called_once()
            mock_mongo.MongoClient.assert_called_once()
            mock_ext.get_db.assert_called_once()


class TestMigrateAdminImportSideEffects(unittest.TestCase):
    """
    Subprocess-isolated verification that importing or aborting migrate_admin.py
    causes zero import-time database side effects (never imports extensions).
    """

    def test_import_migrate_admin_does_not_import_extensions(self):
        code = (
            "import sys; "
            "sys.path.insert(0, 'backend'); "
            "import db.migrate_admin; "
            "assert 'extensions' not in sys.modules, 'extensions was unexpectedly imported at module load'; "
            "assert 'pymongo' not in sys.modules, 'pymongo was unexpectedly imported at module load'; "
            "print('ISOLATED_IMPORT_SUCCESS')"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Subprocess failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
        self.assertIn("ISOLATED_IMPORT_SUCCESS", proc.stdout)

    def test_calling_migrate_admin_without_confirmation_does_not_import_extensions(self):
        code = (
            "import os, sys; "
            "sys.path.insert(0, 'backend'); "
            "os.environ.pop('CONFIRM_ADMIN_MIGRATION', None); "
            "import db.migrate_admin; "
            "db.migrate_admin.migrate_admin(); "
            "assert 'extensions' not in sys.modules, 'extensions was unexpectedly imported during unconfirmed call'; "
            "assert 'pymongo' not in sys.modules, 'pymongo was unexpectedly imported during unconfirmed call'; "
            "print('ISOLATED_UNCONFIRMED_SUCCESS')"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Subprocess failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
        self.assertIn("[ABORTED]", proc.stdout)
        self.assertIn("ISOLATED_UNCONFIRMED_SUCCESS", proc.stdout)

    def test_calling_migrate_admin_with_confirmation_missing_mongo_uri_does_not_import_extensions(self):
        code = (
            "import os, sys; "
            "sys.path.insert(0, 'backend'); "
            "os.environ['CONFIRM_ADMIN_MIGRATION'] = 'true'; "
            "os.environ.pop('MONGO_URI', None); "
            "import db.migrate_admin; "
            "db.migrate_admin.MONGO_URI = ''; "
            "db.migrate_admin.migrate_admin(); "
            "assert 'extensions' not in sys.modules, 'extensions was unexpectedly imported when MONGO_URI was missing'; "
            "assert 'pymongo' not in sys.modules, 'pymongo was unexpectedly imported when MONGO_URI was missing'; "
            "print('ISOLATED_MISSING_URI_SUCCESS')"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Subprocess failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
        self.assertIn("[ERROR] MONGO_URI", proc.stdout)
        self.assertIn("ISOLATED_MISSING_URI_SUCCESS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
