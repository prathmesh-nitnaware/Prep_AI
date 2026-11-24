# PrepAI Intelligence Engine (PIE) — Target Architecture & R0 Foundation

**Status:** Target Architectural Specification  
**Scope:** R0 Foundation & Non-Disruptive Coexistence  
**Document Version:** 1.0.0  

---

## 1. Architectural Philosophy: The Non-Disruptive Control Plane

The **PrepAI Intelligence Engine (PIE)** is designed to serve as the central intelligence and control plane of PrepAI. Rather than serving as another LLM wrapper or replacing the application wholesale, PIE introduces a structured, decoupled orchestration layer capable of coordinating:

- Specialized intelligence modules (Resume, Answer, Behavioral, Adaptive, Coding, Conversation).
- Model registries and versioned artifacts.
- Deterministic heuristic and algorithmic strategies.
- Strongly typed request/result contracts with provenance tracking.
- Task Directed Acyclic Graph (DAG) workflows with bounded retries and concurrency.
- Controlled autonomy and policy enforcement.
- Model performance tracking, validation rubrics, and controlled promotion.

### Non-Disruptive Coexistence Principle
During R0, PIE is implemented as a **modular package inside the existing backend** (`backend/pie/`). It does **not** alter existing database schemas, change API routes, or disrupt unmigrated legacy flows. The existing architecture remains completely untouched unless explicitly routed via the feature flag.

```
                               Incoming Request
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │  Existing Route / Controller   │
                       └───────────────┬───────────────┘
                                       │
                         Is PIE_ENABLED && Migrated?
                                      / \
                                     /   \
                              No    /     \   Yes
                                   /       \
                                  ▼         ▼
             ┌─────────────────────────┐   ┌────────────────────────────────┐
             │   Legacy Implementation │   │          PIE Engine            │
             │   (Existing Orchestrator│   │   (Task DAG, Autonomy Check,   │
             │   & Direct Providers)   │   │    Typed Contracts, Registry)  │
             └────────────┬────────────┘   └───────────────┬────────────────┘
                          │                               │
                          │                               ▼
                          │                ┌────────────────────────────────┐
                          │                │       Intelligence Module      │
                          │                │   (Deterministic / Local ML /  │
                          │                │    Legacy Baseline Adapter)    │
                          │                └───────────────┬────────────────┘
                          │                                │
                          └───────────────┬────────────────┘
                                          │
                                          ▼
                               Validated JSON Response
```

---

## 2. Feature Flag & Fail-Safe Routing Design

The engine is controlled by an explicit environment toggle:
```bash
PIE_ENABLED=false # Default state
```

### Invariant Rules:
1. **Default Off:** If `PIE_ENABLED` is missing, unparseable, or set to `false`, the application operates in 100% legacy mode. Zero PIE code is executed in request pathways.
2. **Explicit Migration Only:** When `PIE_ENABLED=true`, **only explicitly migrated routes** (in R0: solely the resume scoring adapter if enabled) execute through PIE. All other routes continue using their legacy implementations.
3. **Safe Initialization:** If PIE configuration is invalid or the PIE registry fails to load when `PIE_ENABLED=true`, the system fails safely, logging an error and either falling back to the legacy pathway or returning a structured diagnostic error—it must never crash the Flask server startup.
4. **Instant Rollback:** Setting `PIE_ENABLED=false` immediately reverts all traffic to the legacy implementation with zero code changes or database migrations.

---

## 3. Strict Decoupling: Zero External LLM Dependency in PIE

A core requirement of PIE is that **the intelligence engine must not depend on an external LLM being available**:
- **No External LLM Calls in PIE Core:** PIE core components (engine, workflow DAG, policies, registries, validators) will never execute calls to Google Gemini, OpenAI, Anthropic, or any third-party cloud LLM API.
- **Offline Testability:** All unit and regression tests for PIE will execute with zero network connectivity.
- **Baseline Classification for Legacy Integrations:** Existing Gemini and Ollama services remain in the legacy application but are strictly registered as `baseline_only` in PIE's model registry. They cannot be chosen as production providers by PIE's decision engine.
- **Deterministic and Local Strategies First:** Capabilities in PIE will initially leverage deterministic parsing, rule-based heuristics, statistical NLP, and procedural algorithms, with local language models introduced in later phases (R5) only when justified.

---

## 4. Package Structure (`backend/pie/`)

The PIE package is housed entirely within the existing backend without restructuring existing directories:

```text
backend/
    pie/
        __init__.py                 # Public package exports, versioning, factory

        core/
            __init__.py
            engine.py               # Central PIE Engine orchestrator
            config.py               # Strongly validated PIE configuration
            context.py              # Execution context, correlation IDs, trace metadata

        contracts/
            __init__.py
            requests.py             # Strongly typed ModuleRequest schema
            results.py              # Strongly typed ModuleResult schema with provenance
            metadata.py             # ModuleMetadata and ModelMetadata schemas
            exceptions.py           # Domain exception hierarchy (no conflicts with built-ins)

        registry/
            __init__.py
            models.yaml             # Strict YAML model inventory & lifecycle metadata
            model_registry.py       # ModelRegistry loader, schema validator, query API
            module_registry.py      # ModuleRegistry for explicit intelligence module registration
            schemas.py              # Strict Pydantic models for registry validation

        workflow/
            __init__.py
            task.py                 # WorkflowTask definition, policies, retries, timeouts
            graph.py                # TaskDAG graph builder, cycle detection, topological sort
            runner.py               # Concurrent/Sequential DAG execution engine
            state.py                # Task and workflow lifecycle state enums

        policies/
            __init__.py
            autonomy.py             # 3-level autonomy definitions & evaluation engine
            permissions.py          # Capability-based authorization checks (default-deny)

        providers/
            __init__.py
            base.py                 # Abstract ModelProvider interface for future local models

        observability/
            __init__.py
            logging.py              # Structured JSON logging with trace propagation & redaction

        modules/
            __init__.py
            base.py                 # Abstract IntelligenceModule base class
            legacy_resume.py        # Step 9 LegacyResumeModule migration adapter

        api/
            __init__.py
            routes.py               # PIE diagnostic and health blueprint (GET /api/pie/health)

        repositories/
            __init__.py
            interfaces.py           # Abstract state persistence interfaces (Memory + DB)
```

---

## 5. Strongly Typed Contracts (Pydantic v2)

Every boundary in PIE enforces strict type validation using Pydantic v2.

### 5.1 `ModuleRequest`
```python
class ModuleRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    task_type: str
    input_payload: Dict[str, Any]
    context: Dict[str, Any] = Field(default_factory=dict)
    requested_module: Optional[str] = None
    execution_constraints: Dict[str, Any] = Field(default_factory=dict)
```

### 5.2 `ModuleResult` & Provenance
Outputs must explicitly declare the provenance of their data:
- `observed`: Direct measurement or deterministic extraction from raw inputs (e.g. word count, regex match, PDF text).
- `predicted`: Output from a statistical machine learning model or classifier.
- `inferred`: Output derived through heuristic logic, multi-factor deduction, or generative synthesis.

```python
class ProvenanceType(str, Enum):
    OBSERVED = "observed"
    PREDICTED = "predicted"
    INFERRED = "inferred"

class ModuleResult(BaseModel):
    request_id: str
    trace_id: str
    module_id: str
    module_version: str
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    status: Literal["success", "partial", "failure"]
    output_payload: Dict[str, Any]
    provenance: ProvenanceType
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    latency_ms: int
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
```

### 5.3 Exception Hierarchy
All PIE exceptions inherit from `PIEException` and avoid shadowing Python's standard library:
- `PIEException` (Base)
  - `RegistryError`
    - `ModuleNotFoundError`
    - `ModuleUnavailableError`
    - `DuplicateModuleError`
    - `ModelNotFoundError`
    - `ModelUnavailableError`
    - `RegistryValidationError`
  - `ContractError`
    - `InvalidModuleInputError`
    - `InvalidModuleOutputError`
  - `ExecutionError`
    - `ModuleExecutionError`
    - `WorkflowExecutionError`
    - `TaskTimeoutError`
    - `WorkflowCycleError`
  - `SecurityPolicyError`
    - `PolicyViolationError`
    - `UnauthorizedCapabilityError`

---

## 6. Model & Module Registry System

### 6.1 Model Lifecycle Governance
Models are declared declaratively in `backend/pie/registry/models.yaml` and validated strictly against a Pydantic schema:

```yaml
version: "1.0"
models:
  - model_id: "baseline-gemini-2.0-flash"
    version: "2026.1"
    name: "Google Gemini 2.0 Flash Baseline"
    task_type: "general_instruction"
    provider: "google_genai"
    artifact_path: "external://api.google.com"
    dataset: "proprietary_google"
    dataset_version: "2026-01"
    license: "proprietary"
    evaluation_metrics:
      historical_benchmark: 0.88
    status: "baseline_only" # NEVER selected by PIE production engine
    resource_requirements:
      network: "egress_required"
    created_at: "2026-01-01T00:00:00Z"
    rollback_version: null
```

#### Valid Model Lifecycle States:
- `development`: Under active local development and experimentation.
- `evaluation`: Frozen for benchmark evaluation against validation rubrics.
- `approved`: Validated and cleared for deployment; pending activation.
- `production`: Active production model eligible for PIE execution selection.
- `deprecated`: Phased out; retained for historical trace playback only.
- `baseline_only`: External legacy baselines used exclusively for comparative benchmarking; **strictly blocked from production selection**.

### 6.2 Module Registry
Intelligence modules must register explicitly via `module_registry.register(module)`. Attempting to execute an unregistered module or capability is rejected with a `PolicyViolationError` by default.

---

## 7. Workflow Engine: Task DAG Execution

The workflow engine executes complex multi-step intelligence workflows as Directed Acyclic Graphs (DAGs):

```
                        ┌───────────────┐
                        │   Task A:     │
                        │ Resume Parser │
                        └───────┬───────┘
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
                 ▼                             ▼
        ┌─────────────────┐           ┌─────────────────┐
        │    Task B:      │           │    Task C:      │
        │ Skill Extractor │           │ Project Auditor │
        └────────┬────────┘           └────────┬────────┘
                 │                             │
                 └──────────────┬──────────────┘
                                │
                                ▼
                        ┌───────────────┐
                        │    Task D:    │
                        │ ATS Scorer    │
                        └───────────────┘
```

### Engine Capabilities:
1. **DAG Validation & Cycle Detection:** Graph topologies are validated prior to execution using depth-first search cycle detection.
2. **Topological Scheduling:** Independent tasks (e.g. Task B and Task C) execute concurrently via thread pools (`ThreadPoolExecutor`), while dependent tasks await ancestor resolution.
3. **Task Retries & Backoff:** Bounded retries with exponential backoff for transient failures. Non-idempotent operations or policy violations are never retried.
4. **Task Timeout Handling:** Individual task timeouts prevent pipeline hangs.
5. **Structured Task States:** `pending` -> `queued` -> `running` -> `completed` / `failed` / `cancelled` / `retrying`.
6. **Trace Context Propagation:** Unique `trace_id` is propagated from the entry point down to each task execution and log entry.

---

## 8. Autonomy & Execution Policy Engine

PIE implements a **3-tier governance policy**:

| Policy Level | Classification | Allowed Operations | Enforcement |
|---|---|---|---|
| **Level 1** | **Autonomous** | Read-only extraction, parsing, mathematical scoring, heuristic evaluation, in-memory DAG tasks. | Permitted automatically for registered modules adhering to input contracts. |
| **Level 2** | **Policy-Controlled** | Database writes, persistent cache mutations, expensive batch scoring, external storage access. | Checked against caller identity, role authorization, and rate limits. |
| **Level 3** | **Human Approval** | Schema alterations, user data deletion, model promotion to production, irreversible administrative overrides. | Requires explicit human approval confirmation token; rejected safely if approval mechanism is not yet satisfied. |

**Default-Deny Rule:** Unregistered capabilities or modules not explicitly matching the requested policy are immediately denied with `UnauthorizedCapabilityError`.

---

## 9. Step 9 Legacy Migration Target: `LegacyResumeModule`

As specified in the R0 requirements, `POST /api/resume/score` will be the first workflow adapted for PIE:

- **Legacy Route (`PIE_ENABLED=false`):** `backend/routes/resume_score.py:score_resume` directly calls `gemini_service.execute_structured_request`.
- **Migrated Route (`PIE_ENABLED=true`):** The route delegates to `pie_engine.execute(ModuleRequest(task_type="RESUME_SCORING", ...))`.
- **Adapter Implementation (`LegacyResumeModule`):**
  - Executes document extraction via PyMuPDF.
  - Implements deterministic ATS keyword analysis and rubric matching.
  - Returns a `ModuleResult` with `provenance=ProvenanceType.OBSERVED` or `INFERRED`.
  - Maps output exactly to the existing JSON response contract (`score`, `improvement_tips`, `summary`, `missing_keywords`, `strengths`, `weaknesses`).
  - Preserves user authentication, audit logging, and database writes to `resumes` table.
  - **Zero external LLM calls during parity tests.**

---

## 10. Future ML Foundation: R1 to R6 Phasing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ R0: PIE Foundation & Modular Monolith Architecture (Current Phase)           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ R1: Resume Intelligence (Bi-encoder skill matching, LightGBM, SHAP, ONNX)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ R2: Answer Intelligence & Memory (STAR evaluation, NLI, calibrated rubrics) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ R3: Adaptive Interview & Coding Intelligence (IRT, Elo, AST complexity)     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ R4: Multimodal Communication Intelligence (Visual stability, acoustic pace) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ R5: Local Generator & Conversational Intelligence (GGUF, QLoRA, llama.cpp)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ R6: Full System Hardening, Automated Evals & Production Model Promotion     │
└─────────────────────────────────────────────────────────────────────────────┘
```

