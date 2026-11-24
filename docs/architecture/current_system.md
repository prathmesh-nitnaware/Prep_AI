# PrepAI Current System Architecture & Implementation Audit

**Date:** April 2026  
**Auditor:** Senior Backend Architect & Security-Focused Python Engineer  
**Status:** Baseline Completed (Read-Only Audit)  

---

## 1. System Overview & Deployment Topology

PrepAI is an AI-powered technical and behavioral interview preparation platform. While documentation files (`PROJECT_STATE.md` and `README.md`) describe an older architecture based on MongoDB and direct development servers, the actual repository implements a **multi-tier, load-balanced, containerized architecture**:

```
                              ┌─────────────────────────────────────────┐
                              │           Client Web Browser            │
                              │        React 18 + Vite 6 (SPA)          │
                              └────────────────────┬────────────────────┘
                                                   │
                                     HTTP / WS (Port 80/443)
                                                   │
                                                   ▼
                              ┌─────────────────────────────────────────┐
                              │         Edge Reverse Proxy / LB         │
                              │        Nginx (Alpine Container)         │
                              │      Least-Connections Algorithm        │
                              └──────────┬───────────────────┬──────────┘
                                         │                   │
                          / (Frontend)   │                   │ /api/*, /sock/*
                                         ▼                   ▼
                      ┌───────────────────────┐  ┌───────────────────────────────────┐
                      │   Frontend Service    │  │     Backend Cluster Upstream      │
                      │  Nginx Serving Static │  │  backend_1:5000 (Gunicorn gthread)│
                      │      Vite Build       │  │  backend_2:5000 (Gunicorn gthread)│
                      │                       │  │  backend_3:5000 (Gunicorn gthread)│
                      └───────────────────────┘  └─────────────────┬─────────────────┘
                                                                   │
                                                          psycopg2 Connection Pool
                                                                   │
                                                                   ▼
                                                 ┌───────────────────────────────────┐
                                                 │      Neon Serverless PostgreSQL   │
                                                 │    (External Cloud Database, TLS) │
                                                 │   Tables: users, interviews,      │
                                                 │   resumes, coding, ai_usage       │
                                                 └───────────────────────────────────┘
```

### Multi-Instance Production Environment (`docker-compose.yml`)
- **`load_balancer`**: Nginx Alpine instance binding ports 80 and 443, configured with `least_conn` load balancing across three backend instances (`backend_1`, `backend_2`, `backend_3`). Enforces client upload limits (15MB), SSL termination with Certbot ACME support, rate limiting (30 req/s, burst 20), WebSocket upgrade mappings, and downstream security headers.
- **`backend_1`, `backend_2`, `backend_3`**: Three identical Flask backend containers running Gunicorn with `worker_class = "gthread"` (2 workers, 4 threads per worker, 1000 max connections), each exposing port 5000 and identified via `NODE_ID`.
- **`frontend`**: Nginx container serving pre-compiled static assets from the React Vite production build.
- **Self-Contained Dev Proxy (`backend/load_balancer.py`)**: A Python-based fallback HTTP reverse proxy supporting round-robin and least-connections with periodic health checks at `/api/health` and live stats at `/lb-status`.

---

## 2. Actual Technology Stack

| Layer | Documented Technology | Actual Verified Technology | Version / Implementation Details |
|---|---|---|---|
| **Frontend Framework** | React 18 | React 18 | `18.3.1`, React DOM `18.3.1` |
| **Frontend Tooling** | Vite | Vite 6 | `vite@6.4.3`, `@vitejs/plugin-react@4.7.0` |
| **Frontend Routing** | React Router | React Router DOM | `react-router-dom@6.30.6` |
| **Code Editor** | Monaco Editor | Monaco Editor React | `@monaco-editor/react@4.7.0` |
| **Client Computer Vision** | MediaPipe (Python) | Vladmandic Face-API (Browser) | `@vladmandic/face-api@1.7.15` (TinyFaceDetector, WebGL/Wasm) |
| **Client Speech/Voice** | Librosa (Python) | Web Audio API + HTML5 Speech | In-browser Web Audio API (`AudioContext`, `AnalyserNode`) + `webkitSpeechRecognition` |
| **Backend Framework** | Flask | Flask | `flask` (Python 3.11 in Docker, system has Python 3.14) |
| **WSGI Server** | Not documented | Gunicorn | `gunicorn@26.0.0` with `gthread` worker engine |
| **WebSockets** | Socket.IO (claimed in package.json) | flask-sock (Pure WebSockets) | `flask-sock` on backend; native `WebSocket` in browser |
| **Database** | **MongoDB Atlas** (claimed in README/PROJECT_STATE) | **Neon Serverless PostgreSQL** | PostgreSQL 16+ via `psycopg2-binary@2.9.12` with `ThreadedConnectionPool` |
| **AI Gateway** | Ollama / Gemini Beta | Google GenAI SDK + Ollama SDK | `google-genai` SDK (`gemini-2.0-flash`) + `ollama` SDK (`llama3:8b`) |
| **PDF Extraction** | PyMuPDF | PyMuPDF (fitz) | `pymupdf@1.28.2` |
| **Authentication** | JWT | PyJWT | `pyjwt@2.13.0` (HS256 access, verify, reset tokens) |
| **Reverse Proxy** | Single Dev Server | Nginx Alpine / Python Load Balancer | Upstream cluster with `least_conn`, health checks, failover |

---

## 3. Database Architecture & Schema Audit

### 3.1 Database Technology
- **Engine:** PostgreSQL (Serverless on [neon.tech](https://neon.tech))
- **Connection String:** Configured via `DATABASE_URL` environment variable (`postgresql://...?sslmode=require`).
- **Driver:** `psycopg2-binary` using `psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10)`.
- **Resilience:** `get_db()` context manager performs a pre-flight `SELECT 1` liveness probe to recycle stale connections caused by Neon serverless compute suspend/idle timeouts.
- **Transactions:** Auto-commits on clean exit; rolls back on exceptions.
- **Cursor:** `dict_cursor(conn)` yields rows as dictionaries via `RealDictCursor`.
- **Initialization:** Idempotent DDL executed on application startup in `backend/extensions.py:init_db()`.

### 3.2 Verified Table Definitions

#### 1. `users` Table
Stores user accounts, authentication credentials, onboarding state, profile details, and embedded resume data.
```sql
CREATE TABLE IF NOT EXISTS users (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL,
    email                TEXT UNIQUE NOT NULL,
    password_hash        TEXT NOT NULL,
    role                 TEXT DEFAULT 'candidate',
    is_verified          BOOLEAN DEFAULT FALSE,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    bio                  TEXT,
    github               TEXT,
    linkedin             TEXT,
    website              TEXT,
    education            TEXT,
    current_job          TEXT,
    target_job           TEXT,
    resume_filename      TEXT,
    resume_data          TEXT,           -- Base64-encoded raw resume file
    resume_text          TEXT,           -- Plain text extracted via PyMuPDF
    resume_updated_at    TIMESTAMPTZ,
    email_verified       BOOLEAN DEFAULT FALSE,
    email_verified_at    TIMESTAMPTZ,
    verification_email_sent_at TIMESTAMPTZ,
    verification_email_send_count INTEGER DEFAULT 0,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
```

#### 2. `interviews` Table
Stores interview sessions, questions, answers, deterministic and AI evaluations, and telemetry.
```sql
CREATE TABLE IF NOT EXISTS interviews (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID REFERENCES users(id) ON DELETE CASCADE,
    role              TEXT,
    experience        TEXT,
    focus             TEXT,
    difficulty        TEXT DEFAULT 'Medium',
    status            TEXT DEFAULT 'active',   -- 'active' | 'completed'
    overall_score     INTEGER,                 -- 0-100 aggregated score
    category_scores   JSONB DEFAULT '{}',      -- Clarity, Technical, Confidence, etc.
    evaluation_status TEXT DEFAULT 'completed',
    report            JSONB DEFAULT NULL,      -- Full structured final report
    questions         JSONB DEFAULT '[]',      -- Array of generated question objects
    answers           JSONB DEFAULT '[]',      -- Array of evaluated candidate answers
    interview_state   JSONB DEFAULT '{}',      -- Adaptive stage state machine
    strategy          JSONB DEFAULT '{}',      -- Dynamic stage strategy map
    resume_context    TEXT DEFAULT '',
    recording_url     TEXT DEFAULT '',
    job_description   TEXT DEFAULT '',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
```

#### 3. `resumes` Table
Historical log of resume ATS scoring runs.
```sql
CREATE TABLE IF NOT EXISTS resumes (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT,
    score      INTEGER,
    summary    TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 4. `coding_submissions` Table
Log of coding challenges submitted to the Coding Dojo.
```sql
CREATE TABLE IF NOT EXISTS coding_submissions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(id) ON DELETE CASCADE,
    challenge_id     TEXT,
    code             TEXT,
    success          BOOLEAN DEFAULT FALSE,
    clarity_score    INTEGER,
    confidence_score INTEGER,
    feedback         TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

#### 5. `ai_usage` Table
Comprehensive telemetry and cost governance table logging every AI request.
```sql
CREATE TABLE IF NOT EXISTS ai_usage (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id             UUID REFERENCES interviews(id) ON DELETE SET NULL,
    user_id                  UUID REFERENCES users(id) ON DELETE SET NULL,
    request_type             TEXT NOT NULL,    -- QUESTION_GENERATION, ANSWER_EVALUATION, etc.
    model                    TEXT,
    provider                 TEXT DEFAULT 'gemini',
    prompt_version           TEXT DEFAULT 'v1',
    pricing_version          TEXT DEFAULT 'google_gemini_2026_01',
    pricing_effective_date   TEXT DEFAULT '2026-01-01',
    input_price_per_million  NUMERIC(10, 6) DEFAULT 0.10,
    output_price_per_million NUMERIC(10, 6) DEFAULT 0.40,
    status                   TEXT NOT NULL,    -- 'success' | 'failed'
    input_tokens             INTEGER,
    output_tokens            INTEGER,
    total_tokens             INTEGER,
    input_cost               NUMERIC(10, 6) DEFAULT 0.0,
    output_cost              NUMERIC(10, 6) DEFAULT 0.0,
    estimated_cost           NUMERIC(10, 6) DEFAULT 0.0,
    latency_ms               INTEGER,          -- Total request latency
    provider_latency_ms      INTEGER,          -- Raw AI provider latency
    retry_delay_ms           INTEGER DEFAULT 0,
    retry_count              INTEGER DEFAULT 0,
    cache_hit                BOOLEAN DEFAULT FALSE,
    validation_failed        BOOLEAN DEFAULT FALSE,
    truncation_detected      BOOLEAN DEFAULT FALSE,
    created_at               TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Complete API Inventory

The application registers 8 blueprints and multiple root endpoints under the `/api` namespace:

### 4.1 System & Diagnostic Endpoints (`backend/main.py`)
| Endpoint | Method | Auth | Request Body | Response Schema | Purpose |
|---|---|---|---|---|---|
| `/api/health` | GET | None | None | `{"status": "production-ready", "ai": "active"}` | Cluster health probe |
| `/api/metrics` | GET | None | None | `{"cache": {...}, "rate_limiter": {...}}` | Internal cache & rate limiter statistics |
| `/api/lb-test`, `/lb-test` | GET | None | None | `{"status": "ok", "backend": node_id, "hostname": hostname}` | Node diagnostic for load balancer verification |
| `/api/<path:path>` | OPTIONS | None | None | `{"status": "ok"}` with CORS headers | Preflight CORS handler |
| `/api/v1/interview/stream` | WS | Query `?token=` or message | `{"text": str, "role": str}` | Token-streamed AI responses (`{"type": "token", "content": str}`) | Real-time WebSocket interview chat |

### 4.2 Authentication (`backend/routes/auth.py`, Prefix: `/api/auth`)
| Endpoint | Method | Auth | Rate Limit | Request Body | Response Schema | DB Operation |
|---|---|---|---|---|---|---|
| `/signup` | POST | None | Yes | `{"email": str, "password": str, "name": str}` | `{"message": str, "email_verification_required": bool}` (201) | `INSERT INTO users` |
| `/login` | POST | None | Yes | `{"email": str, "password": str}` | `{"token": str, "user": {...}}` (200) | `SELECT * FROM users WHERE email = %s` |
| `/verify-email` | POST | None | Yes | `{"token": str}` | `{"message": str, "verified": true}` (200) | `UPDATE users SET is_verified = TRUE...` |
| `/resend-verification` | POST | None | Yes | `{"email": str}` | `{"message": str, "email_verification_disabled": true}` (200) | No-op (Verification disabled) |
| `/me` | GET | Bearer JWT | No | None | `{"user": {...}}` (200) | `SELECT * FROM users WHERE email = %s` |
| `/forgot-password` | POST | None | Yes | `{"email": str}` | `{"message": str}` (200) | Sends password reset email if user exists |
| `/reset-password` | POST | None | Yes | `{"token": str, "password": str}` | `{"message": str}` (200) | `UPDATE users SET password_hash = %s` |
| `/google` | POST | None | Yes | `{"email": str, "name": str, "google_id": str}` | `{"token": str, "user": {...}}` (200) | Upserts user, returns JWT |

### 4.3 Interview Lifecycle (`backend/routes/interview.py`, Prefix: `/api/interview`)
| Endpoint | Method | Auth | Rate Limit | Request Body | Response Schema | Downstream Operations |
|---|---|---|---|---|---|---|
| `/resume-context` | GET | Bearer JWT | No | None | `{"has_resume": bool, "resume_text": str, "resume_filename": str}` | Reads user resume from `users` table |
| `/initiate` | POST | Bearer JWT | Yes | `{"role": str, "experience": str, "focus": str, "difficulty": str, "resume_context": str, "job_description": str, "question_count": int}` | `{"session": dict, "session_id": str, "question": dict, "first_question": dict}` | Calls `orchestrator.initiate_interview()`, creates record in `interviews`, generates initial question set via Gemini |
| `/submit` | POST | Bearer JWT | Yes | `{"session_id": str, "question": dict|str, "question_id": int, "answer": str, "signals": dict}` | `{"feedback": {"score": int, "clarity": int, "technical": int, "confidence": int, "strengths": list, "improvements": list, "ideal_answer": str}}` | Evaluates answer via Gemini + deterministic scoring, updates `interviews.answers` using `FOR UPDATE` lock |
| `/next` | POST | Bearer JWT | Yes | `{"session_id": str, "current_index": int}` | `{"question": dict, "completed": bool}` | Resolves stage strategy, generates next adaptive question or marks interview complete |
| `/complete` | POST | Bearer JWT | Yes | `{"session_id": str}` | `{"success": true, "report": dict}` | Calls `orchestrator.get_or_generate_final_report()`, synthesizes final scorecard |
| `/report/<session_id>` | GET | Bearer JWT | No | None | `{"report": dict, "success": true}` | Retrieves cached report or generates on demand |
| `/session/<session_id>/telemetry` | GET | Bearer JWT | No | None | `{"total_cost": float, "total_tokens": int, "invocations": list}` | Aggregates telemetry from `ai_usage` table |
| `/history` | GET | Bearer JWT | No (Cached 45s) | None | `[{"id": str, "role": str, "experience": str, "overall_score": int, ...}]` | Queries completed sessions for current user |
| `/delete/<session_id>` | DELETE | Bearer JWT | No | None | `{"success": true}` | `DELETE FROM interviews WHERE id = %s AND user_id = %s` |
| `/session/<session_id>` | GET | Bearer JWT | No | None | Detailed session dictionary including questions, answers, state | `SELECT * FROM interviews WHERE id = %s AND user_id = %s` |
| `/upload-recording` | POST | Bearer JWT | No | Multipart: `session_id`, `recording` (file) | `{"success": true, "recording_url": str}` | Saves webm video to `uploads/recordings/` (**Bug: missing `os` import**) |

### 4.4 Resume Scoring (`backend/routes/resume_score.py`, Prefix: `/api/resume`)
| Endpoint | Method | Auth | Rate Limit | Request Body | Response Schema | Downstream Operations |
|---|---|---|---|---|---|---|
| `/score` | POST | Bearer JWT | Yes | Multipart: `resume` (PDF/DOCX/TXT), `role`, `job_description` | `{"score": int, "improvement_tips": list, "summary": str, "missing_keywords": list, "strengths": list, "weaknesses": list}` | Extracts text via PyMuPDF, prompts Gemini for ATS analysis, saves to `resumes` table |

### 4.5 Coding Dojo (`backend/routes/coding.py`, Prefix: `/api/coding`)
| Endpoint | Method | Auth | Rate Limit | Request Body | Response Schema | Downstream Operations |
|---|---|---|---|---|---|---|
| `/challenges` | GET | Bearer JWT | No | None | List of curated algorithmic challenges | Reads in-memory `CHALLENGES` list |
| `/challenge/<id>` | GET | Bearer JWT | No | None | Single challenge details | Reads in-memory `CHALLENGES` list |
| `/submit` | POST | Bearer JWT | Yes | `{"challenge_id": str, "code": str, "language": str, "action": str}` | `{"success": bool, "clarity_score": int, "confidence_score": int, "feedback": str, "suggestions": list}` | Prompts Gemini for code review; saves to `coding_submissions` |
| `/leaderboard` | GET | Bearer JWT | No | None | Top 20 users by solved challenges | SQL aggregation join between `coding_submissions` and `users` |

### 4.6 User Profile & Resume Vault (`backend/routes/profile.py`, Prefix: `/api/profile`)
| Endpoint | Method | Auth | Rate Limit | Request Body | Response Schema | DB Operation |
|---|---|---|---|---|---|---|
| `/resume/upload` | POST | Bearer JWT | Yes | Multipart: `resume` (PDF/DOCX/TXT) | `{"success": true, "filename": str, "extracted_text": str}` | Extracts text via PyMuPDF, base64 encodes, updates `users` record |
| `/resume/get` | GET | Bearer JWT | No | None | `{"has_resume": bool, "resume_filename": str, "resume_data": str, "resume_text": str}` | `SELECT * FROM users WHERE id = %s` |
| `/resume/delete` | DELETE | Bearer JWT | No | None | `{"success": true, "message": str}` | Clears resume columns in `users` record |
| `/update` | PUT | Bearer JWT | No | `{"name": str, "bio": str, "target_job": str, ...}` | `{"message": "Profile updated successfully"}` | Updates whitelisted profile fields in `users` |

### 4.7 Support Chatbot (`backend/routes/chatbot.py`, Prefix: `/api/chatbot`)
| Endpoint | Method | Auth | Rate Limit | Request Body | Response Schema | Downstream Operations |
|---|---|---|---|---|---|---|
| `/ask` | POST | Bearer JWT | Yes | `{"message": str}` | `{"reply": str}` | Prompts Gemini with scoped PrepAI platform context |

### 4.8 Administration (`backend/routes/admin.py`, Prefix: `/api/admin`)
| Endpoint | Method | Auth | Request Body | Response Schema | Downstream Operations |
|---|---|---|---|---|---|
| `/analytics` | GET | Admin JWT | None | `{"total_users": int, "chart_data": list}` | Aggregates 7-day registration curve |
| `/users` | GET | Admin JWT | None | `{"users": list}` | Candidate directory with interview counts and problem stats |
| `/user/<id>/activity` | GET | Admin JWT | None | `{"user": dict, "stats": dict, "timeline": list, ...}` | Deep-dive activity chronology for selected candidate |
| `/ai/metrics` | GET | Admin JWT | Query: `?period=today\|week\|month` | `{"total_spend": float, "total_tokens": int, "model_breakdown": dict, ...}` | Aggregates spend, token consumption, and cost anomalies |

### 4.9 Dashboard (`backend/routes/dashboard.py`, Prefix: `/api/dashboard`)
| Endpoint | Method | Auth | Request Body | Response Schema | Status |
|---|---|---|---|---|---|
| `/` | GET | Bearer JWT | None | `{"user": str, "stats": {"interviews": 0, "avg_score": 0}}` | Legacy stub; actual metrics computed by frontend from `/api/interview/history` |

---

## 5. Existing Orchestration Flow Audit

### 5.1 Request Lifecycle
1. **Network Ingress:** Request reaches Nginx reverse proxy on port 80/443.
2. **Reverse Proxy Inspection:**
   - Enforces rate limiting (`limit_req zone=api_limit burst=20 nodelay`).
   - Injects security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`).
   - Balances request to upstream backend cluster (`prepai_backend_cluster`) using `least_conn`.
3. **WSGI Concurrency:** Handled by Gunicorn with `gthread` workers (2 processes × 4 threads).
4. **Flask Application Entry (`main.py`):**
   - Applies structured request logging via `register_request_logger`.
   - Injects CORS headers on every response via `@app.after_request`.
   - Routes request to matching Blueprint.
5. **Route Middleware:**
   - `@rate_limit`: Checks client IP against `InMemoryRateLimiterBackend` (token-bucket: capacity 60, refill 15/s).
   - `@token_required`: Decodes JWT Bearer token using `Config.SECRET_KEY`, validates token purpose is `access`, loads user record from Neon DB.
   - `@cache_response`: Checks `InMemoryCacheBackend` for cached JSON response (isolated per user).
6. **Execution in `InterviewOrchestrator` (`services/ai/orchestrator.py`):**
   - Implements PostgreSQL row-level locking (`SELECT ... FOR UPDATE`) to prevent race conditions during concurrent answer submissions.
   - Merges candidate answer, stage strategy, and real-time audio/video HUD metrics.
   - Invokes `gemini_service.execute_structured_request()`:
     - Routes request to appropriate model via `model_router.select_model()`.
     - Sets strict max output tokens via `get_max_output_tokens()`.
     - Attempts call to Google GenAI (`gemini-2.0-flash`).
     - On failure or rate limit: retries with exponential backoff up to `MAX_AI_RETRIES` (2 retries).
     - On permanent failure / timeout: falls back to local Ollama (`llama3:8b`).
     - Cleans markdown/JSON fences and validates response against typed schema function (`validate_answer_evaluation()`).
     - Records token usage, latency breakdown, pricing version, and estimated cost to `ai_usage` table.
   - Computes deterministic score aggregation and updates `interviews` table.
7. **Response Egress:** Response formatted as JSON and returned to client.

---

## 6. Discrepancies Between Documentation and Implementation

| Item | Documented Claim (README / PROJECT_STATE) | Actual Code Implementation | Severity |
|---|---|---|---|
| **Database** | Claims **MongoDB Atlas** across README, banners, and PROJECT_STATE. | Entire codebase migrated to **Neon Serverless PostgreSQL** with `psycopg2`. Old `mongodb_data/` folder abandoned at root. | **High** |
| **Backend Entry Point** | `PROJECT_STATE.md` states: `python backend/app.py`. | `backend/app.py` does not exist. The actual entry point is `backend/main.py`. | **Medium** |
| **Default AI Provider** | Claims default is `ollama` with `llama3:8b`. | Default is `gemini` (`gemini-2.0-flash`) with Ollama only configured as an offline fallback. | **Medium** |
| **Code Execution Engine** | README claims "Neural Monaco IDE with automated space/time complexity reviews". | There is **no code execution sandbox**. Code is passed as plain text to an LLM prompt for review. `JudgeService` in `app/services/judge_service.py` is an unintegrated placeholder with a fake API key. | **Medium** |
| **ML Signal Pipelines** | README claims MediaPipe Pose, OpenCV solvePnP, and Librosa YIN process candidate streams in backend. | Scripts in `ml/` are **not imported anywhere**. Video/audio processing is entirely client-side in the browser via `@vladmandic/face-api` and Web Audio API. | **High** |
| **Missing Backend Files** | README lists `routes/dojo.py`, `utils/ai_helpers.py`, `utils/audio_helpers.py`, `utils/cv_helpers.py`, `models/database.py`. | None of these files exist. The actual files are `routes/coding.py`, `services/ai/gemini_service.py`, `models/user_model.py`, and `extensions.py`. | **Medium** |
| **Requirements List** | README claims `requirements.txt` contains `PyMongo, Librosa`. | Neither `pymongo` nor `librosa` are present in `backend/requirements.txt`. | **Low** |
| **WebSocket Protocol** | `frontend/package.json` includes `socket.io-client`. | Backend uses `flask-sock` (native WebSocket protocol), NOT Socket.IO. Frontend uses native browser `WebSocket`. | **Low** |

---

## 7. Technical Debt Inventory

1. **Missing `import os` in `backend/routes/interview.py` (Line 358):** The `/upload-recording` endpoint attempts to call `os.path.join` and `os.makedirs`, but `os` is never imported in the file, causing a runtime `NameError: name 'os' is not defined`.
2. **Hardcoded MongoDB Scripts in PostgreSQL Codebase:**
   - `backend/scripts/init_db.py`: Still imports `from extensions import db, client` and attempts to create MongoDB collections.
   - `backend/scripts/setup_admin.py`: Imports `from extensions import users_collection` and uses MongoDB `insert_one` / `update_one`.
   - `backend/verify_all_users.py`: Imports `from extensions import users_collection` and uses MongoDB `update_many`.
   - `ml/nlp/resume_parser.py`: Imports `from backend.ollama_client import generate_response`, which does not exist.
   - `backend/db/migrate_admin.py`: Hardcoded MongoDB migration script containing hardcoded plaintext password references (`admin123`).
3. **Frontend Property Mismatch in Admin Activity Query:**
   - `frontend/src/pages/AdminDashboard.jsx` (Line 116) and `AdminUsersList.jsx` (Line 78) call:
     ```javascript
     api.client.get(`/api/admin/user/${targetUser._id}/activity`)
     ```
     Because the PostgreSQL API returns `id` (not `_id`), `targetUser._id` evaluates to `undefined`, requesting `/api/admin/user/undefined/activity`.
4. **Hardcoded Secrets & Dev Defaults:**
   - `backend/config.py`: Hardcoded default fallback `SECRET_KEY = "prepai_local_dev_secret_key_2026_minimum_32_bytes_long"`.
   - `backend/app/services/judge_service.py`: Hardcoded `API_KEY = "REPLACE_WITH_YOUR_KEY"`.
   - `backend/scripts/setup_admin.py`: Hardcoded `admin_email = "admin@gmail.com"`, `admin_password = "admin123"`.
5. **Abandoned Local Artifacts:**
   - `mongodb_data/`: Contains WiredTiger files from previous MongoDB installation.
   - `backend/test_out.txt` and `backend/test_out_utf8.txt`: Tracked in Git, containing raw connection error logs with MongoDB Atlas hostnames.
   - `training/create_dataset.py` & `training/training.py`: Generates fake synthetic data (`fake_interview_data.csv`) and trains a toy RandomForest that is never deployed or used.
   - `ml/nlp/answer_evaluator.py`: Completely empty 0-byte file.
6. **Python Runtime Inconsistency:**
   - `backend/.venv` was created with `Python 3.12.10`, but its base interpreter path `C:\Users\Admin\AppData\Local\Python\pythoncore-3.12-64\python.exe` is missing.
   - The active system Python in PATH is `Python 3.14.4` (`C:\Users\Admin\AppData\Local\Programs\Python\Python314\python.exe`).
   - System Python lacks `flask`, `flask-cors`, `flask-sock`, causing scripts run with `python <file>` to fail immediately.

---

## 8. Existing Security Audit Findings

| Severity | Issue | Location | Evidence / Description |
|---|---|---|---|
| **High** | Hardcoded default admin credentials | `backend/scripts/setup_admin.py`, `backend/db/migrate_admin.py` | Admin email `admin@gmail.com` and password `admin123` hardcoded in plain text. |
| **High** | Insecure fallback `SECRET_KEY` | `backend/config.py:7` | If `SECRET_KEY` environment variable is not supplied, falls back to a predictable static string in source code. |
| **Medium** | Client IP spoofing vulnerability in rate limiter | `backend/utils/middleware.py:73` | Reads `X-Forwarded-For` without validating proxy trust, allowing external clients to forge IP headers and evade rate limiting. |
| **Medium** | Potential file upload exhaustion | `backend/routes/interview.py:363` | `/upload-recording` saves `.webm` files directly to local disk (`uploads/recordings/`) without quota checks, disk space validation, or automatic cleanup. |
| **Low** | Tracked test logs containing internal hostnames | `backend/test_out.txt`, `backend/test_out_utf8.txt` | Tracked in Git; contains MongoDB Atlas cluster shard hostnames and TLS error dumps. |
| **Low** | Fake API Key placeholder in unused code | `backend/app/services/judge_service.py:10` | Hardcoded `API_KEY = "REPLACE_WITH_YOUR_KEY"`. |

