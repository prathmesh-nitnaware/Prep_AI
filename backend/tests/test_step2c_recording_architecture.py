"""
test_step2c_recording_architecture.py — Focused Tests for Step 2C Recording Architecture
========================================================================================
Validates Option 1: Client-Side Only Recording Architecture:
1. POST /api/interview/upload-recording consistently returns HTTP 410 Gone.
2. Response payload adheres strictly to the approved contract:
   - "error": "Server-side recording upload is permanently disabled. Recordings are saved locally on the candidate device."
   - "code": "RECORDING_UPLOAD_DISABLED"
3. Empty, JSON, and multipart requests all receive HTTP 410 without payload parsing.
4. Route does not access request.form or request.files.
5. No filesystem directories or video files are created on disk.
6. Zero database connections, cursors, or queries are executed.
7. Endpoint requires no authentication and consistently returns 410 (never 401 or 500).
8. Source analysis verifies frontend contains zero uploadInterviewRecording references.
9. Source analysis verifies frontend preserves candidate device WebM download and completion navigation.
"""

import os
import sys
import io
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend directory is first in sys.path and venv site-packages is appended
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE_PACKAGES = os.path.join(BACKEND_DIR, ".venv", "Lib", "site-packages")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if os.path.exists(SITE_PACKAGES) and SITE_PACKAGES not in sys.path:
    sys.path.append(SITE_PACKAGES)

# Mock psycopg2 pool connection to prevent sandbox socket network errors
try:
    import psycopg2.pool
    psycopg2.pool.ThreadedConnectionPool = MagicMock()
except ImportError:
    pass

from flask import Flask
from routes.interview import interview_bp


class TestStep2CBackendUploadEndpoint(unittest.TestCase):
    """Test backend HTTP 410 Gone behavior for /api/interview/upload-recording."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(interview_bp, url_prefix="/api/interview")
        self.client = self.app.test_client()

    def test_upload_recording_returns_410_gone(self):
        resp = self.client.post("/api/interview/upload-recording")
        self.assertEqual(resp.status_code, 410)

    def test_upload_recording_json_contract(self):
        resp = self.client.post("/api/interview/upload-recording")
        self.assertEqual(resp.status_code, 410)
        data = resp.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(
            data.get("error"),
            "Server-side recording upload is permanently disabled. Recordings are saved locally on the candidate device."
        )
        self.assertEqual(data.get("code"), "RECORDING_UPLOAD_DISABLED")

    def test_upload_recording_empty_json_multipart_all_receive_410(self):
        # 1. Empty body
        resp_empty = self.client.post("/api/interview/upload-recording")
        self.assertEqual(resp_empty.status_code, 410)

        # 2. JSON body
        resp_json = self.client.post(
            "/api/interview/upload-recording",
            json={"session_id": "test_session_123"}
        )
        self.assertEqual(resp_json.status_code, 410)

        # 3. Multipart form data with simulated video blob
        multipart_data = {
            "session_id": "test_session_123",
            "recording": (io.BytesIO(b"\x1a\x45\xdf\xa3webm_fake_header"), "recording.webm"),
        }
        resp_multipart = self.client.post(
            "/api/interview/upload-recording",
            data=multipart_data,
            content_type="multipart/form-data"
        )
        self.assertEqual(resp_multipart.status_code, 410)
        self.assertEqual(resp_multipart.get_json().get("code"), "RECORDING_UPLOAD_DISABLED")

    def test_upload_recording_does_not_access_request_form_or_files(self):
        """Ensure application-level code does not evaluate request.form or request.files."""
        with patch("flask.Request.form", new_callable=unittest.mock.PropertyMock) as mock_form, \
             patch("flask.Request.files", new_callable=unittest.mock.PropertyMock) as mock_files:

            resp = self.client.post("/api/interview/upload-recording")
            self.assertEqual(resp.status_code, 410)
            mock_form.assert_not_called()
            mock_files.assert_not_called()

    def test_upload_recording_creates_no_filesystem_artifacts(self):
        """Ensure no upload directory or file is ever created on server disk."""
        uploads_recordings_path = os.path.join(BACKEND_DIR, "uploads", "recordings")

        with patch("os.makedirs") as mock_makedirs:
            resp = self.client.post(
                "/api/interview/upload-recording",
                data={"session_id": "s_1", "recording": (io.BytesIO(b"data"), "rec.webm")},
                content_type="multipart/form-data"
            )
            self.assertEqual(resp.status_code, 410)
            mock_makedirs.assert_not_called()

        # If the directory doesn't exist, verify it wasn't created
        # If it does exist historically, verify no new file was placed inside
        self.assertFalse(
            os.path.exists(os.path.join(uploads_recordings_path, "recording_s_1.webm")),
            "Recording file was unexpectedly written to disk"
        )

    def test_upload_recording_executes_no_database_operations(self):
        """Verify endpoint makes zero database connections or queries."""
        with patch("extensions.get_db") as mock_get_db:
            resp = self.client.post("/api/interview/upload-recording")
            self.assertEqual(resp.status_code, 410)
            mock_get_db.assert_not_called()

    def test_upload_recording_requires_no_auth_header(self):
        """Verify endpoint consistently returns 410 without requiring Authorization tokens."""
        resp = self.client.post(
            "/api/interview/upload-recording",
            headers={"Authorization": ""}  # Explicitly empty / unauthenticated
        )
        self.assertEqual(resp.status_code, 410)
        self.assertNotEqual(resp.status_code, 401)


class TestStep2CFrontendSourceIntegrity(unittest.TestCase):
    """Verify frontend source files have zero upload calls and preserve local downloads."""

    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(BACKEND_DIR, ".."))
        self.interview_live_path = os.path.join(self.repo_root, "frontend", "src", "pages", "InterviewLive.jsx")
        self.api_service_path = os.path.join(self.repo_root, "frontend", "src", "services", "api.js")

    def test_frontend_contains_zero_upload_interview_recording_references(self):
        """Verify uploadInterviewRecording is completely removed from InterviewLive.jsx and api.js."""
        with open(self.interview_live_path, "r", encoding="utf-8") as f:
            live_content = f.read()
        self.assertNotIn(
            "uploadInterviewRecording",
            live_content,
            "InterviewLive.jsx unexpectedly still references uploadInterviewRecording"
        )

        with open(self.api_service_path, "r", encoding="utf-8") as f:
            api_content = f.read()
        self.assertNotIn(
            "uploadInterviewRecording",
            api_content,
            "api.js unexpectedly still defines uploadInterviewRecording"
        )

    def test_frontend_preserves_local_webm_download_logic(self):
        """Verify candidate device auto-download logic is fully preserved in finishAndProcessRecording."""
        with open(self.interview_live_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check key components of candidate local download
        self.assertIn("URL.createObjectURL(blob)", content)
        self.assertIn("PrepAI_Interview_", content)
        self.assertIn(".webm", content)
        self.assertIn("a.download", content)
        self.assertIn("a.click()", content)
        self.assertIn("URL.revokeObjectURL(url)", content)

    def test_frontend_preserves_interview_completion_and_navigation(self):
        """Verify finishAndProcessRecording and navigation to report are preserved on completion."""
        with open(self.interview_live_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("await finishAndProcessRecording()", content)
        self.assertIn("navigate('/interview/report'", content)
        self.assertIn("currentQIndex >= MAX_QUESTIONS", content)


if __name__ == "__main__":
    unittest.main()
