# Step 2 Execution Plan: Security & Configuration Cleanup

**Date:** April 2026  
**Status:** Proposal — Awaiting User Approval to Execute  
**Scope:** Strict Phase Gating — Security & Configuration Hardening Only  

---

## 1. Overview & Guiding Principles

Step 2 addresses verified security risks, runtime defects, and obsolete artifacts identified during the Step 1 reconciliation.
- **Zero Business Logic Redesign:** Does not alter existing interview scoring, coding dojo logic, or authentication semantics.
- **Zero Schema Migrations:** Does not alter existing Neon PostgreSQL database tables or columns.
- **Reversible & Minimal:** Every change is atomic, verifiable, and carries an immediate rollback procedure.

---

## 2. Prioritized Task Breakdown

### Task 1 (Priority: HIGH) — Enforce Explicit `SECRET_KEY` & Add PIE Flag
- **Target Files:**
  - [`backend/config.py`](file:///d:/Prep_AI/backend/config.py#L6-L10)
  - [`backend/.env.example`](file:///d:/Prep_AI/backend/.env.example)
- **Problem:**
  [`backend/config.py:7`](file:///d:/Prep_AI/backend/config.py#L7) sets a hardcoded default fallback:
  `SECRET_KEY = os.getenv("SECRET_KEY", "prepai_local_dev_secret_key_2026_minimum_32_bytes_long")`.
  In production, if `SECRET_KEY` is omitted, the application silently boots using a known, public secret key. Furthermore, the feature flag `PIE_ENABLED` is not yet defined in configuration.
- **Planned Modification:**
  1. In `backend/config.py`:
     - Load `PIE_ENABLED = os.getenv("PIE_ENABLED", "false").lower() in ("true", "1", "t")` (Default: `False`).
     - In production (`ENVIRONMENT=production`), raise a fatal `RuntimeError("SECRET_KEY must be explicitly configured in production")` if `SECRET_KEY` is missing or matches the default development placeholder.
     - In development, retain a safe, logged development-only warning if `SECRET_KEY` is unset.
  2. In `backend/.env.example`:
     - Add `PIE_ENABLED=false` with descriptive comments.
- **Risks:** Missing `SECRET_KEY` in production container will intentionally prevent startup.
- **Verification Tests:**
  - Test boot with `ENVIRONMENT=development` and unset `SECRET_KEY` -> Boots with warning.
  - Test boot with `ENVIRONMENT=production` and unset `SECRET_KEY` -> Raises `RuntimeError`.
  - Test `PIE_ENABLED` resolution for `"true"`, `"false"`, `""` -> Resolves to boolean correctly.
- **Rollback:** Revert `backend/config.py` and `backend/.env.example` via `git checkout`.

---

### Task 2 (Priority: HIGH) — Fix Missing `import os` in `routes/interview.py`
- **Target File:**
  - [`backend/routes/interview.py`](file:///d:/Prep_AI/backend/routes/interview.py#L1-L20)
- **Problem:**
  [`backend/routes/interview.py:358`](file:///d:/Prep_AI/backend/routes/interview.py#L358) calls `os.path.join` and `os.makedirs`, but `import os` is absent from imports, causing runtime `NameError` and HTTP 500 on all recording uploads.
- **Planned Modification:**
  Add `import os` to top-level imports in `backend/routes/interview.py`.
- **Risks:** Negligible. Resolves a deterministic runtime crash.
- **Verification Tests:**
  - Invoke `POST /api/interview/upload-recording` with test multipart form data.
  - Confirm handler resolves directory path without `NameError`.
- **Rollback:** Remove `import os` line.

---

### Task 3 (Priority: MEDIUM) — Trusted Proxy Resolution & Rate Limiter Hardening
- **Target Files:**
  - [`backend/main.py`](file:///d:/Prep_AI/backend/main.py#L34-L45)
  - [`backend/utils/middleware.py`](file:///d:/Prep_AI/backend/utils/middleware.py#L71-L86)
- **Problem:**
  [`backend/utils/middleware.py:73`](file:///d:/Prep_AI/backend/utils/middleware.py#L73) takes the first item of `X-Forwarded-For` without proxy validation, allowing clients to forge arbitrary IP headers and bypass rate limits.
- **Planned Modification:**
  1. In `backend/main.py`: Apply Werkzeug's `ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)` when `is_production` is True, ensuring that `request.remote_addr` is correctly set by trusted reverse proxies (Nginx).
  2. In `backend/utils/middleware.py`: Use `request.remote_addr or "0.0.0.0"` as the authoritative client IP.
- **Risks:** If proxy hop count is misconfigured, rate limits may group all requests under proxy internal IP.
- **Verification Tests:**
  - Send request with spoofed `X-Forwarded-For: 10.99.99.99` -> Rate limiter tracks actual socket address.
  - Exceed rate limit capacity -> Verifies HTTP 429 is returned.
- **Rollback:** Remove `ProxyFix` wrapping in `main.py` and restore previous line in `middleware.py`.

---

### Task 4 (Priority: MEDIUM) — Reconcile Frontend User ID Property Mismatch
- **Target Files:**
  - [`frontend/src/pages/AdminDashboard.jsx`](file:///d:/Prep_AI/frontend/src/pages/AdminDashboard.jsx#L116)
  - [`frontend/src/pages/AdminUsersList.jsx`](file:///d:/Prep_AI/frontend/src/pages/AdminUsersList.jsx#L78)
- **Problem:**
  Both files invoke `api.client.get('/api/admin/user/' + targetUser._id + '/activity')`. Because PostgreSQL returns `id` instead of MongoDB's `_id`, this requests `/api/admin/user/undefined/activity`, triggering a 404 in the administration view.
- **Planned Modification:**
  Update URL construction to:
  ```javascript
  const userId = targetUser.id || targetUser._id;
  const res = await api.client.get(`/api/admin/user/${userId}/activity`);
  ```
- **Risks:** Zero. Backwards-compatible with both PostgreSQL and legacy MongoDB objects.
- **Verification Tests:**
  - Click a candidate row in Admin Users list -> Activity popup opens with HTTP 200 activity data.
- **Rollback:** Revert both files via `git checkout`.

---

### Task 5 (Priority: LOW) — Sanitize Hardcoded Credentials in Obsolete Scripts
- **Target Files:**
  - [`backend/scripts/setup_admin.py`](file:///d:/Prep_AI/backend/scripts/setup_admin.py)
  - [`backend/db/migrate_admin.py`](file:///d:/Prep_AI/backend/db/migrate_admin.py)
  - [`backend/app/services/judge_service.py`](file:///d:/Prep_AI/backend/app/services/judge_service.py)
- **Problem:**
  Plaintext credentials `admin@gmail.com` / `admin123` and placeholder keys `REPLACE_WITH_YOUR_KEY` are hardcoded in source control.
- **Planned Modification:**
  1. In `setup_admin.py`: Read credentials exclusively from `os.getenv("ADMIN_EMAIL")` and `os.getenv("ADMIN_PASSWORD")`. Refuse execution if unset.
  2. In `migrate_admin.py`: Remove printed password strings; read credentials from environment variables.
  3. In `judge_service.py`: Read `API_KEY = os.getenv("JUDGE0_API_KEY", "")`.
- **Risks:** Zero. These scripts are not part of runtime request paths.
- **Verification Tests:**
  - Scan repository for plaintext password strings -> Zero matches.
- **Rollback:** Revert files via `git checkout`.

---

### Task 6 (Priority: LOW) — Untrack Historical Connection Logs from Git Index
- **Target Files:**
  - `backend/test_out.txt`
  - `backend/test_out_utf8.txt`
- **Problem:**
  Both files are tracked in Git index despite matching `.gitignore`. They contain legacy MongoDB Atlas shard URLs and TLS error messages.
- **Planned Modification:**
  Execute `git rm --cached backend/test_out.txt backend/test_out_utf8.txt`.
  Ensure they remain excluded by `.gitignore`.
- **Risks:** Zero. Does not affect application runtime.
- **Verification Tests:**
  - `git ls-files backend/test_out.txt` returns empty.
- **Rollback:** `git add backend/test_out.txt backend/test_out_utf8.txt`.

---

## 3. Step 2 Execution Protocol

```
1. Verify Working Directory is clean (main branch, HEAD: 8f8f426).
2. Create baseline tag: git tag baseline-v1.
3. Create feature branch: git checkout -b feature/pie-r0.
4. Execute Task 1 (Config & Feature Flag).
5. Execute Task 2 (Missing import os).
6. Execute Task 3 (ProxyFix & Rate Limiter IP).
7. Execute Task 4 (Frontend targetUser.id).
8. Execute Task 5 (Sanitize scripts).
9. Execute Task 6 (Untrack test_out logs).
10. Run regression & lint checks.
11. Commit changes: security: harden configuration and sanitize legacy artifacts.
12. STOP and present Step 2 completion report for approval prior to Step 3.
```

