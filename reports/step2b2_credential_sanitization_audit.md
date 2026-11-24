# PrepAI PIE R0 — Step 2B.2: Credential Sanitization Audit Report

**Date:** 2026-11-08  
**Status:** READ-ONLY AUDIT & IMPLEMENTATION PLAN (Awaiting Explicit Approval)  
**Scope:** `backend/scripts/setup_admin.py`, `backend/db/migrate_admin.py`, `backend/app/services/judge_service.py`, `backend/config.py`, `backend/.env.example`, `.gitignore`

---

## 1. Executive Security Verdict

The codebase demonstrates sound credential handling for primary production services (`DATABASE_URL`, `GEMINI_API_KEY`, `MAIL_PASSWORD`, `SECRET_KEY`), which are read from environment variables and not committed in tracked configuration files. Furthermore, `.gitignore` comprehensively excludes `.env`, `backend/.env`, and `frontend/.env`.

However, the audit identified **four concrete credential risks** in auxiliary, legacy, and orphaned modules:
1. **Hardcoded Admin Credentials in Setup Script** ([`backend/scripts/setup_admin.py`](file:///d:/Prep_AI/backend/scripts/setup_admin.py#L11-L12)): Static default admin credentials (`admin@gmail.com` / `[REDACTED_DEFAULT_PASSWORD]`) are hardcoded.
2. **Plaintext Password Exposure in Migration Logs** ([`backend/db/migrate_admin.py`](file:///d:/Prep_AI/backend/db/migrate_admin.py#L63)): A print statement outputs `Password: [REDACTED_DEFAULT_PASSWORD]` directly to stdout upon migration.
3. **Hardcoded Placeholder RapidAPI Key & Missing Fail-Closed Guard** ([`backend/app/services/judge_service.py`](file:///d:/Prep_AI/backend/app/services/judge_service.py#L10)): `API_KEY = "REPLACE_WITH_YOUR_KEY"` is hardcoded, never reads from the environment, and transmits this dummy key over external networks to RapidAPI headers without failing closed when credentials are absent.
4. **Internal Cluster Information Leak in Tracked Dev Logs** ([`backend/test_out.txt`](file:///d:/Prep_AI/backend/test_out.txt#L2)): Historical MongoDB Atlas shard hostnames are tracked in source control.

**Remediation Urgency**: Medium-High for hygiene and compliance. None of the audited auxiliary scripts are executed by the live application runtime (`create_app()` / `routes/`), but they represent technical debt and risk of credential exposure if invoked by operators.

---

## 2. Files Inspected

### Primary Files Inspected
1. [`backend/scripts/setup_admin.py`](file:///d:/Prep_AI/backend/scripts/setup_admin.py) *(referenced in prompt as `backend/setup_admin.py`)*
2. [`backend/db/migrate_admin.py`](file:///d:/Prep_AI/backend/db/migrate_admin.py) *(referenced in prompt as `backend/migrate_admin.py`)*
3. [`backend/app/services/judge_service.py`](file:///d:/Prep_AI/backend/app/services/judge_service.py) *(referenced in prompt as `backend/services/ai/judge_service.py`)*

### Supporting & Configuration Files Inspected
4. [`backend/config.py`](file:///d:/Prep_AI/backend/config.py)
5. [`backend/.env.example`](file:///d:/Prep_AI/backend/.env.example)
6. [`.gitignore`](file:///d:/Prep_AI/.gitignore)
7. [`backend/extensions.py`](file:///d:/Prep_AI/backend/extensions.py)
8. [`backend/routes/admin.py`](file:///d:/Prep_AI/backend/routes/admin.py)
9. [`backend/routes/coding.py`](file:///d:/Prep_AI/backend/routes/coding.py)
10. [`backend/utils/auth_helpers.py`](file:///d:/Prep_AI/backend/utils/auth_helpers.py)
11. [`backend/test_out.txt`](file:///d:/Prep_AI/backend/test_out.txt) and [`backend/test_out_utf8.txt`](file:///d:/Prep_AI/backend/test_out_utf8.txt)
12. [`scripts/setup_env.ps1`](file:///d:/Prep_AI/scripts/setup_env.ps1) and [`scripts/run_ollama.ps1`](file:///d:/Prep_AI/scripts/run_ollama.ps1)

---

## 3. Findings Grouped by Severity

### HIGH SEVERITY
- **SEC-2B2-01: Hardcoded Default Admin Credentials in Setup Script**
  - **File & Line**: [`backend/scripts/setup_admin.py:11-12`](file:///d:/Prep_AI/backend/scripts/setup_admin.py#L11-L12)
  - **Type**: Hardcoded username and default plaintext password.
  - **Status**: Obsolete / Broken (script crashes on import due to PyMongo removal), but provides a known attack vector if someone repairs the database connection.
  - **Impact**: If an operator runs this script or adapts it for PostgreSQL, it sets the admin password to a widely known static default (`[REDACTED_DEFAULT_PASSWORD]`).
  - **Remediation**: Remove hardcoded credentials. Read `ADMIN_EMAIL` and `ADMIN_PASSWORD` from environment variables, or require interactive prompt.

### MEDIUM SEVERITY
- **SEC-2B2-02: Plaintext Password Emitted to Terminal/Logs**
  - **File & Line**: [`backend/db/migrate_admin.py:63`](file:///d:/Prep_AI/backend/db/migrate_admin.py#L63)
  - **Type**: Plaintext credential printing to stdout.
  - **Status**: Obsolete (one-time migration script).
  - **Impact**: Terminal outputs and CI/CD logs capture the plaintext administrator password.
  - **Remediation**: Eliminate the line printing the plaintext password.

- **SEC-2B2-03: Hardcoded Placeholder API Key & Lack of Fail-Closed Validation**
  - **File & Line**: [`backend/app/services/judge_service.py:10,29`](file:///d:/Prep_AI/backend/app/services/judge_service.py#L10)
  - **Type**: Hardcoded placeholder API key (`API_KEY = "REPLACE_WITH_YOUR_KEY"`).
  - **Status**: Unused / Orphaned (no active routes import or invoke `JudgeService`).
  - **Impact**: If executed, the service sends dummy credentials over the public Internet to RapidAPI (`X-RapidAPI-Key: REPLACE_WITH_YOUR_KEY`). It lacks environment variable loading and fails open to an external network request instead of failing closed locally.
  - **Remediation**: Load `RAPIDAPI_KEY` from `os.getenv("RAPIDAPI_KEY")` (or `JUDGE0_API_KEY`). Fail closed immediately if key is missing or matches placeholder without making network requests.

### LOW / INFORMATIONAL
- **SEC-2B2-04: Historical Cluster Endpoints in Tracked Debug Logs**
  - **File & Line**: [`backend/test_out.txt:2`](file:///d:/Prep_AI/backend/test_out.txt#L2)
  - **Type**: Infrastructure reconnaissance data (MongoDB Atlas shard hostnames).
  - **Status**: Obsolete debug artifact.
  - **Impact**: Discloses historical database cluster topology.
  - **Remediation**: Maintain in `.gitignore` (already ignored, but previously tracked).

---

## 4. Credential Exposure Inventory

| Ref ID | File & Line | Credential Type | Redacted Sample | Runtime Status | Risk Level |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CRE-01** | `backend/scripts/setup_admin.py:11` | Admin Email | `admin@***.***` | Obsolete (Broken Import) | Low |
| **CRE-02** | `backend/scripts/setup_admin.py:12` | Admin Password | `[REDACTED_DEV_PWD]` | Obsolete (Broken Import) | High |
| **CRE-03** | `backend/db/migrate_admin.py:63` | Admin Password Print | `[REDACTED_DEV_PWD]` | Obsolete | Medium |
| **CRE-04** | `backend/app/services/judge_service.py:10` | API Key Placeholder | `REPLACE_WITH_***` | Orphaned / Unused | Medium |
| **CRE-05** | `backend/config.py:30` | Default Dev Secret Key | `prepai_local_dev_***` | Active Fallback (Protected by 2A warning) | Low |

---

## 5. Compatibility & Status of Administrator Scripts

### A. `backend/scripts/setup_admin.py`
- **Current Compatibility**: **INCOMPATIBLE & BROKEN**.
  - Line 7 attempts: `from extensions import users_collection`.
  - When the project migrated from PyMongo to Neon PostgreSQL (`psycopg2`), `users_collection` was removed from [`backend/extensions.py`](file:///d:/Prep_AI/backend/extensions.py).
  - Attempting to execute `python backend/scripts/setup_admin.py` immediately throws `ImportError: cannot import name 'users_collection' from 'extensions'`.
- **Database Modification Capability**: None in its current state.
- **Embedded Credentials**: Contains hardcoded email `admin@gmail.com` and password `[REDACTED_DEFAULT_PASSWORD]`.
- **Recommendation**: Disarm the script safely:
  1. Remove hardcoded credentials.
  2. Read `ADMIN_EMAIL` and `ADMIN_PASSWORD` from environment variables (`os.getenv`).
  3. Update to use `get_db()` with PostgreSQL `INSERT ... ON CONFLICT (email) DO UPDATE` or guard it with an explicit notice that administration accounts are provisioned via environment variables.

### B. `backend/db/migrate_admin.py`
- **Current Compatibility**: **OBSOLETE**.
  - Purpose: One-time migration script to transfer existing admin users from MongoDB Atlas to Neon PostgreSQL.
  - Dependencies: Requires `pymongo`, `certifi`, and a valid `MONGO_URI`.
  - If `MONGO_URI` is unset, `MongoClient("")` fails.
  - If executed successfully against MongoDB, it creates/updates the admin record in Neon PostgreSQL.
- **Database Modification Capability**: Capable of writing to PostgreSQL if given a valid MongoDB connection string.
- **Embedded Credentials**: Does not hardcode the password in database queries (reads `password_hash` from MongoDB), but line 63 prints the assumed plaintext password `[REDACTED_DEFAULT_PASSWORD]` to stdout.
- **Recommendation**:
  1. Remove line 63 (`print("   Password: ...")`).
  2. Add a safeguard requiring an explicit confirmation flag or environment variable before running.

---

## 6. Judge Service (`JudgeService`) Key Handling Assessment

- **Current Implementation** ([`backend/app/services/judge_service.py`](file:///d:/Prep_AI/backend/app/services/judge_service.py)):
  ```python
  class JudgeService:
      JUDGE0_URL = "https://judge0-ce.p.rapidapi.com"
      API_KEY = "REPLACE_WITH_YOUR_KEY" # Should be in .env
  ```
- **Live Usage**: None. [`backend/routes/coding.py`](file:///d:/Prep_AI/backend/routes/coding.py#L11-L16) uses `gemini_service` for technical challenge evaluation; `JudgeService` is completely disconnected.
- **Defects Identified**:
  1. Does not inspect `os.getenv("RAPIDAPI_KEY")` or `os.getenv("JUDGE0_API_KEY")`.
  2. Invoking `JudgeService.execute()` initiates an unauthenticated outbound HTTP POST to `https://judge0-ce.p.rapidapi.com/submissions` with `"X-RapidAPI-Key": "REPLACE_WITH_YOUR_KEY"`.
  3. Fails open to external network failure instead of failing closed locally.
- **Recommended Fail-Closed Behavior**:
  1. Load key from `Config.RAPIDAPI_KEY` / `os.getenv("RAPIDAPI_KEY")`.
  2. If the key is absent, empty, or equals `"REPLACE_WITH_YOUR_KEY"`, fail closed immediately:
     - Log a structured warning: `"Judge0 code execution engine is not configured; failing closed"`.
     - Return `{"error": "Code execution engine is not configured."}` without dispatching any network request.

---

## 7. Environment & Git Safety Assessment

1. **Git Tracking of `.env` Files**:
   - Inspected via `git ls-files "*.env*"`.
   - Result: Only `backend/.env.example` and `frontend/.env.example` are tracked.
   - [`.gitignore`](file:///d:/Prep_AI/.gitignore#L7-L15) explicitly ignores `.env`, `.env.*`, `backend/.env`, `backend/.env.*`, `frontend/.env`, `frontend/.env.*`.
2. **Missing Environment Documentation**:
   - `RAPIDAPI_KEY` (or `JUDGE0_API_KEY`) is not documented in `backend/.env.example`.
   - `ADMIN_EMAIL` and `ADMIN_PASSWORD` are not documented in `backend/.env.example`.
3. **Historical Commit History**:
   - Per mandatory constraints, no Git history rewriting will take place.

---

## 8. Exact Proposed File Changes (Step 2B.2)

### A. `backend/app/services/judge_service.py`
- Import `os` and `logging`.
- Retrieve API key dynamically:
  ```python
  API_KEY = os.getenv("RAPIDAPI_KEY", os.getenv("JUDGE0_API_KEY", ""))
  ```
- In `execute()`:
  ```python
  if not cls.API_KEY or cls.API_KEY.strip() == "REPLACE_WITH_YOUR_KEY":
      logger.warning("Judge0 code execution key is not configured; execution request failed closed")
      return {"error": "Code execution engine is not configured."}
  ```

### B. `backend/scripts/setup_admin.py`
- Remove hardcoded credentials.
- Read credentials from environment variables:
  ```python
  admin_email = os.getenv("ADMIN_EMAIL", "").strip()
  admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
  if not admin_email or not admin_password:
      print("[ERROR] ADMIN_EMAIL and ADMIN_PASSWORD environment variables are required.")
      return
  ```
- Update database query to use modern Neon PostgreSQL connection (`from extensions import get_db`) instead of obsolete `users_collection`.
- Never print plaintext passwords.

### C. `backend/db/migrate_admin.py`
- Delete line 63 (`print("   Password: ...")`).
- Replace with:
  ```python
  print("   Password: [PRESERVED_FROM_SOURCE_DATABASE]")
  ```

### D. `backend/config.py`
- Add optional configuration attributes:
  ```python
  RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", os.getenv("JUDGE0_API_KEY", ""))
  ```

### E. `backend/.env.example`
- Document optional Judge0 credentials:
  ```bash
  # Optional RapidAPI / Judge0 Code Execution
  RAPIDAPI_KEY=
  ```
- Document initial admin setup variables:
  ```bash
  # Administrator Setup (Optional utility)
  ADMIN_EMAIL=
  ADMIN_PASSWORD=
  ```

---

## 9. Risks & Backward-Compatibility Considerations

1. **Risk of Breaking Active Functionality**:
   - **Zero risk**: Neither `setup_admin.py`, `migrate_admin.py`, nor `judge_service.py` are imported or called by the live Flask web application.
2. **Database Integrity**:
   - No schema changes or migrations will be introduced.
3. **Fail-Closed Behavior**:
   - Ensures that any future attempt to call `JudgeService` without configuring credentials will fail immediately and locally, rather than leaking dummy headers to RapidAPI.

---

## 10. Proposed Implementation & Rollback Plan

### Implementation Sequence:
1. Update `backend/app/services/judge_service.py` with fail-closed key validation.
2. Sanitize `backend/scripts/setup_admin.py` to require environment credentials and use PostgreSQL.
3. Remove plaintext password output from `backend/db/migrate_admin.py`.
4. Update `backend/config.py` and `backend/.env.example`.
5. Author focused tests in `backend/tests/test_step2b2_credential_sanitization.py`.
6. Run full regression test suite (`test_step2a_config.py`, `test_step2b1_ip_rate_limiter.py`, `test_step2b2_credential_sanitization.py`).

### Rollback Plan:
If any unintended side-effects occur, revert the modified files using Git checkout on the specific files:
```powershell
git checkout backend/app/services/judge_service.py backend/scripts/setup_admin.py backend/db/migrate_admin.py backend/config.py backend/.env.example
```
Delete `backend/tests/test_step2b2_credential_sanitization.py`.

---

## 11. Test Cases & Acceptance Criteria

### Test Cases planned for `backend/tests/test_step2b2_credential_sanitization.py`:
1. **JudgeService Fail-Closed without Key**:
   - `RAPIDAPI_KEY` unset -> returns `{"error": "Code execution engine is not configured."}` without making network calls.
2. **JudgeService Fail-Closed with Placeholder Key**:
   - `RAPIDAPI_KEY="REPLACE_WITH_YOUR_KEY"` -> returns `{"error": "Code execution engine is not configured."}` without making network calls.
3. **JudgeService Outbound Execution with Valid Key**:
   - Mocked RapidAPI response: ensures valid key is passed in `X-RapidAPI-Key`.
4. **Setup Admin Environment Requirement**:
   - Running setup admin with missing `ADMIN_EMAIL` or `ADMIN_PASSWORD` fails safely without modifying database.
5. **Log Non-Disclosure**:
   - Verify that neither setup admin, migration, nor judge service logs plaintext passwords or secret keys.

---

## 12. Files Explicitly Excluded from Modification

The following files are strictly out of scope for Step 2B.2:
- All database migration scripts and schema definitions (`backend/extensions.py`).
- All active route controllers (`backend/routes/auth.py`, `backend/routes/coding.py`, `backend/routes/interview.py`, etc.).
- All frontend source files (`frontend/`).
- Deployment manifests (`docker-compose.yml`, `nginx/nginx.conf`, `Dockerfile`).
- All Step 2C recording files (`backend/routes/interview.py`, `frontend/src/pages/Interview.jsx`).
- Git history (`.git`).
- Historical tracked test logs (`backend/test_out.txt`).

---

**AUDIT COMPLETE. STOPPED as instructed. Awaiting your review and explicit approval before implementing any changes.**

