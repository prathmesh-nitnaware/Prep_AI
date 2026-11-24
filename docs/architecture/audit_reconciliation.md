# Audit Reconciliation Report: PrepAI R0 Foundation

**Date:** April 2026  
**Auditor:** Senior Backend Architect, AI/ML Systems Engineer & Security-Focused Python Engineer  
**Status:** Complete (Read-Only Reconciliation)  

---

## 1. Git State & Working Tree Verification

### 1.1 Verified Git Status
- **Current HEAD Commit:** `8f8f4260149177fb915f762d11c0a0e5e1dd1685`
- **Commit Message:** `docs: add SETUP.md — local development setup guide`
- **Active Branch:** `main` (synchronized with `origin/main`)
- **Tracked File Modifications:** **ZERO.** No tracked files have uncommitted modifications (`git diff` is completely clean).

### 1.2 Untracked Files Catalog
The working tree contains several untracked directories and files created prior to or during the audit:
1. `backend/services/ai/local_question_engine.py` (User's experimental procedural question generation algorithm)
2. `ml/nlp/resume_engine.py` (User's experimental regex/taxonomy-based ATS scoring script)
3. `scripts/test_question_engine.py` (Local test runner for `local_question_engine.py`)
4. `scripts/capture_all_pages.js`, `scripts/capture_cdp.js`, `scripts/capture_test.js`, `scripts/debug_admin.js`, `scripts/test_file_capture.js` (Headless browser test and screenshot capture scripts)
5. `chrome-capture-profile/`, `chrome-cdp-profile/`, `chrome-temp-test/`, `chrome-test/` (Chromium browser test session profiles and cache directories)
6. `screenshots/` (Visual testing output artifacts)
7. `docs/architecture/` (Architectural deliverables from Step 1)

**Rule Enforced:** No untracked user files have been deleted, moved, modified, or staged.

---

## 2. Reconciling the 26 vs. 38 Route Discrepancy

In the initial audit report, a summary headline cited "26 routes" while the accompanying enumerated list detailed 38 distinct endpoints. A rigorous audit of the code resolves this discrepancy:

### Exact Breakdown:
- **Registered Functional HTTP Blueprints:** 8 blueprints in [`backend/routes/__init__.py`](file:///d:/Prep_AI/backend/routes/__init__.py).
- **Blueprint Route Handlers:** 34 distinct view handler functions across the 8 blueprints.
  - `admin_bp` (`/api/admin`): 4 handlers (`/analytics`, `/users`, `/user/<user_id>/activity`, `/ai/metrics`).
  - `auth_bp` (`/api/auth`): 8 handlers (`/signup`, `/login`, `/verify-email`, `/resend-verification`, `/me`, `/forgot-password`, `/reset-password`, `/google`).
  - `chatbot_bp` (`/api/chatbot`): 1 handler (`/ask`).
  - `coding_bp` (`/api/coding`): 4 handlers (`/challenges`, `/challenge/<challenge_id>`, `/submit`, `/leaderboard`).
  - `dashboard_bp` (`/api/dashboard`): 1 handler (`/`).
  - `interview_bp` (`/api/interview`): 11 handlers (`/resume-context`, `/initiate`, `/submit`, `/next`, `/complete`, `/report/<session_id>` [also aliased to `/session/<session_id>/report`], `/session/<session_id>/telemetry`, `/history`, `/delete/<session_id>`, `/session/<session_id>`, `/upload-recording`).
  - `profile_bp` (`/api/profile`): 4 handlers (`/resume/upload`, `/resume/get`, `/resume/delete`, `/update`).
  - `resume_bp` (`/api/resume`): 1 handler (`/score`).
- **Main Application Handlers (`main.py`):** 4 distinct view functions:
  - `handle_options` (`/api/<path:path>` [OPTIONS])
  - `health` (`/api/health`)
  - `metrics` (`/api/metrics`)
  - `lb_test` (`/api/lb-test` and `/lb-test`)
- **WebSocket Handlers (`interview_socket.py`):** 1 handler (`/api/v1/interview/stream`).
- **Total View Handler Functions:** **39 distinct Python functions** (34 blueprint + 4 main + 1 WebSocket).
- **Total URL Map Rules:** **42 rules** (34 blueprint handlers + 1 dual alias rule on `/session/<session_id>/report` + 1 dual alias rule on `/lb-test` + 4 main rules + 1 Flask static rule `/static/<filename>` + 1 WebSocket route).

**Conclusion:** The number "26" was a typographical under-count in the initial report summary headline; exactly **38 user-facing API endpoints** (37 HTTP + 1 WebSocket) exist in the application.

---

## 3. Recording Data Flow & Runtime Defect Verification

### 3.1 Verified Lifecycle
1. **Capture:** In [`frontend/src/pages/InterviewLive.jsx:114-125`](file:///d:/Prep_AI/frontend/src/pages/InterviewLive.jsx#L114-L125), `MediaRecorder` captures audio and video streams at 1000ms chunks as `video/webm;codecs=vp9`.
2. **Local Download:** Upon interview conclusion ([`InterviewLive.jsx:152-163`](file:///d:/Prep_AI/frontend/src/pages/InterviewLive.jsx#L152-L163)), `finishAndProcessRecording()` automatically triggers a browser download of `PrepAI_Interview_<sessionId>.webm`.
3. **Network Ingress:** The frontend calls `api.uploadInterviewRecording(sessionId, blob)` ([`frontend/src/services/api.js:192`](file:///d:/Prep_AI/frontend/src/services/api.js#L192)), issuing a `POST /api/interview/upload-recording` with multipart form data (`session_id`, `recording`).
4. **Nginx Ingress Limit:** [`nginx/nginx.conf:40`](file:///d:/Prep_AI/nginx/nginx.conf#L40) enforces `client_max_body_size 15M;`. Recordings exceeding 15MB are rejected by Nginx with `413 Request Entity Too Large`.
5. **Runtime Crash on Backend:** In [`backend/routes/interview.py:358`](file:///d:/Prep_AI/backend/routes/interview.py#L358), the handler executes:
   ```python
   recordings_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "recordings")
   ```
   **`import os` is missing from `backend/routes/interview.py`.**
   This triggers an uncaught `NameError: name 'os' is not defined`. The exception is caught by the generic `except Exception as e:` block, which returns HTTP 500:
   `{"error": "Failed to upload session recording"}`.
6. **Client Error Masking:** [`InterviewLive.jsx:171`](file:///d:/Prep_AI/frontend/src/pages/InterviewLive.jsx#L171) catches the error and silently resolves `null`. The user receives their local file download, but the recording is **never stored on the server**, and `recording_url` is **never updated in the database**.

---

## 4. Resume Scoring: Corrected Migration Strategy

### 4.1 What Gemini Actually Does
[`backend/services/ai/prompts.py:381-439`](file:///d:/Prep_AI/backend/services/ai/prompts.py#L381-L439) instructs Gemini to act as a "brutally honest Technical Recruiter, ATS Auditor, and Hiring Manager":
- It writes contextual narrative summaries of candidate-job alignment.
- It identifies soft-skill fluff and specific phrases to delete (`items_to_delete`).
- It generates rewritten bullet points with action verbs and metrics (`bullet_improvements`: `original` vs `optimized`).
- It generates qualitative interview focus areas tailored to the candidate's skill gaps.

### 4.2 Realistic Migration Contract for PIE R0
**Deterministic scoring is NOT semantically equivalent to Gemini.**
A rule-based or regex engine (such as `ml/nlp/resume_engine.py`) cannot perform generative bullet rewriting or nuanced semantic critiques without a language model.
- **R0 Scope:** The `LegacyResumeModule` in R0 is an **architectural routing and pipeline proof**, NOT an AI replacement for Gemini.
- **Provenance Tagging:** Outputs must explicitly tag deterministic extractions as `OBSERVED` (e.g. extracted skills, word count) and heuristic fallback data as `INFERRED` / `SYNTHETIC`.
- **No Mock LLM Pretending:** R0 tests will verify contract conformance, schema validation, and DAG routing using deterministic fixtures. We will not claim that R0 replaces generative recruiting intelligence. Full semantic equivalence is explicitly deferred to R1 (Bi-encoders/LightGBM) and R5 (Local LLMs).

---

## 5. Controlled Feature Flag Behavior

### 5.1 Invariants
- `PIE_ENABLED=false` (Default): 100% legacy routing. PIE code is completely inert.
- `PIE_ENABLED=true`: Only explicitly migrated endpoints (`POST /api/resume/score` in R0) execute through PIE. Unmigrated endpoints execute their existing code paths.

### 5.2 Controlled Failure vs. Silent Fallback
**Strict Rule:** If `PIE_ENABLED=true` and a migrated request fails in PIE (e.g., module unavailable, policy violation, DAG execution error), **the system MUST NOT silently dispatch a background call to Gemini or Ollama.**
- A silent fallback masks defects, breaks isolation, creates non-deterministic billing/latency, and violates the core principle of eliminating external LLM dependencies.
- When PIE fails, it must fail cleanly: log structured diagnostics with `trace_id` and return an explicit HTTP 503/500 error indicating PIE pipeline failure, or a clearly labeled deterministic degraded result.

---

## 6. Comprehensive Security Analysis

1. **JWT Revocation & Expiration:**
   - HS256 tokens have a 24-hour expiration ([`backend/routes/auth.py:89`](file:///d:/Prep_AI/backend/routes/auth.py#L89)).
   - There is no server-side token blacklist or session version column in the database.
   - If an account password is changed or a user clicks "Logout", existing issued tokens remain valid until the 24-hour TTL expires.
2. **Insecure Default Secret Key:**
   - [`backend/config.py:7`](file:///d:/Prep_AI/backend/config.py#L7) sets a hardcoded default string if `SECRET_KEY` is not present in `.env`. Anyone with source code access can sign administrative JWTs if this default is used.
3. **IP Spoofing via `X-Forwarded-For`:**
   - [`backend/utils/middleware.py:73`](file:///d:/Prep_AI/backend/utils/middleware.py#L73) splits `X-Forwarded-For` by comma and takes index `[0]`.
   - Any external client can bypass the in-memory token-bucket rate limiter by sending random IP addresses in the `X-Forwarded-For` header. Werkzeug's `ProxyFix` is not registered.
4. **Obsolete Admin Scripts with Hardcoded Credentials:**
   - [`backend/scripts/setup_admin.py`](file:///d:/Prep_AI/backend/scripts/setup_admin.py) and [`backend/db/migrate_admin.py`](file:///d:/Prep_AI/backend/db/migrate_admin.py) hardcode `admin@gmail.com` and `admin123`.
   - Both scripts attempt to import non-existent MongoDB extensions and crash if executed.
5. **Local Recording Storage Vulnerability:**
   - Local directory storage in container environments causes multi-instance inconsistency across `backend_1`, `backend_2`, `backend_3`, and creates a potential disk exhaustion vector.
6. **Tracked Production Connection Logs:**
   - `backend/test_out.txt` and `backend/test_out_utf8.txt` are tracked in Git and contain raw MongoDB Atlas shard domain names and TLS handshake errors.

---

## 7. Verified Docker Runtime & Dependency Configuration

- **Docker Backend Base Image:** `python:3.11-slim` in [`backend/Dockerfile`](file:///d:/Prep_AI/backend/Dockerfile).
- **Docker Compose Topology:** 3 backend instances behind Nginx on port 5000 (`docker-compose.yml`).
- **Gunicorn Concurrency:** 2 workers, 4 threads (`gthread`), 1000 max connections ([`backend/gunicorn.conf.py`](file:///d:/Prep_AI/backend/gunicorn.conf.py)).
- **Host System Runtime:** Python 3.14.4 installed at `C:\Users\Admin\AppData\Local\Programs\Python\Python314\python.exe`.
- **Stale Host Virtualenv:** `backend/.venv` references a missing Python 3.12 binary (`C:\Users\Admin\AppData\Local\Python\pythoncore-3.12-64\python.exe`).
- **Pydantic Availability:** Pydantic `2.13.4` is installed in the system Python environment, verifying compatibility with PIE's typed contract requirements.

