# PrepAI Intelligence Engine (PIE) R0 — Step 3A: Core Architecture Design

**Status:** APPROVED ARCHITECTURAL SPECIFICATION (READ-ONLY DESIGN)  
**Phase:** PIE R0 Foundation — Step 3A  
**Target Package:** `backend/pie/`  
**Document Date:** November 2026  
**Implementation Phase:** Step 3B (Pending Explicit Approval)  

---

## 1. Architectural Mission & Core Principles

The **PrepAI Intelligence Engine (PIE)** is the centralized intelligence and orchestration control plane of PrepAI. Rather than operating as an uncoordinated collection of autonomous agents or an unprincipled LLM wrapper, PIE introduces a deterministic, strongly typed, modular orchestration architecture designed for non-disruptive coexistence alongside the existing PrepAI Flask application.

### Guiding Principles:
1. **Centralized Orchestration, Not Competing Agents:** PIE controls execution via deterministic Task Directed Acyclic Graphs (DAGs), explicit capability dispatch, and bounded in-process execution.
2. **Non-Disruptive Coexistence:** PIE resides inside `backend/pie/`. When `PIE_ENABLED=false` (the default), zero PIE code is loaded or executed in active request pathways. Existing legacy endpoints continue operating with 100% parity.
3. **Zero Production External LLM Dependency in Core:** PIE core (contracts, registries, workflow runner, policy enforcement, evaluators) is 100% offline, deterministic, and self-contained. It makes zero calls to Google Gemini, Ollama, OpenAI, or third-party cloud APIs.
4. **Zero Unrestricted Execution:** No dynamic shell commands (`os.system`, `subprocess`), no arbitrary SQL queries, and no dynamic code evaluation (`eval()`, `exec()`) are permitted within PIE modules or contracts.
5. **In-Process Simplicity (No Distributed Complexity):** Execution is strictly synchronous and in-process using bounded thread pools (`concurrent.futures.ThreadPoolExecutor`). No Celery, Redis, Kafka, or distributed broker daemons are introduced in R0.
6. **Zero Schema Migrations in R0:** PIE R0 requires no database migrations. All persistence is handled by existing database tables through legacy adapters when explicitly invoked.

---

## 2. Proposed Package Tree

The PIE core framework will be placed entirely within `backend/pie/` with clean boundaries separating contracts, registries, workflow orchestration, execution engine, security policy, evaluation, and health diagnostics:

```text
backend/
└── pie/
    ├── __init__.py                     # Package version, exports, and safe initialization hook
    │
    ├── contracts/                      # Strongly typed data transfer schemas & exceptions
    │   ├── __init__.py                 # Public contract exports
    │   ├── context.py                  # ExecutionContext (trace_id, request_id, user_id, deadline_mono, timeout_seconds)
    │   ├── task.py                     # TaskDefinition, TaskInput, TaskOutput, ProvenanceType
    │   ├── workflow.py                 # WorkflowDefinition, ExecutionPlan, StageDefinition
    │   ├── results.py                  # ExecutionResult, TaskResult, StepStatus
    │   └── exceptions.py               # Domain exception hierarchy (no shadow of built-ins)
    │
    ├── registry/                       # Declarative model & in-process module registries
    │   ├── __init__.py                 # Registry exports
    │   ├── models.json                 # Canonical static JSON model & baseline inventory (models.yaml optional)
    │   ├── schemas.py                  # ModelMetadata, CapabilityMetadata, ProviderConfig
    │   ├── model_registry.py           # ModelRegistry (loads, validates, and queries model inventory)
    │   └── module_registry.py          # ModuleRegistry (registers in-process intelligence modules)
    │
    ├── workflow/                       # Graph representation, cycle detection & scheduling
    │   ├── __init__.py                 # Workflow exports
    │   ├── dag.py                      # TaskDAG (nodes, directed edges, graph builder)
    │   ├── validator.py                # Graph cycle detection (DFS 3-color), orphan detection
    │   └── ordering.py                 # Deterministic topological sort & stage partitioner
    │
    ├── engine/                         # In-process execution runner & task dispatcher
    │   ├── __init__.py                 # Engine exports
    │   ├── runner.py                   # In-process synchronous/thread-bounded TaskRunner
    │   ├── dispatcher.py               # TaskDispatcher (matches capability to module handler)
    │   ├── executor.py                 # Bounded execution with timeout & retry arithmetic
    │   └── result_builder.py           # Constructs structured ExecutionResult with metrics
    │
    ├── policy/                         # Security boundaries & capability authorization
    │   ├── __init__.py                 # Policy exports
    │   ├── permissions.py              # CapabilityPermissions (default-deny permission sets)
    │   ├── guard.py                    # ExecutionGuard (enforces capability boundaries)
    │   └── rules.py                    # PolicyRules (forbids raw SQL, shell execution, socket egress)
    │
    ├── evaluation/                     # Deterministic evaluation & failure telemetry
    │   ├── __init__.py                 # Evaluation exports
    │   ├── recorder.py                 # OutcomeRecorder (captures latency, status, error trace)
    │   ├── evaluators.py               # DeterministicEvaluator (schema conformance, bounds checks)
    │   └── taxonomy.py                 # ErrorClassifier (transient, contract, policy, internal)
    │
    └── health/                         # Diagnostic readiness & registry validation
        ├── __init__.py                 # Health exports
        ├── checker.py                  # EngineHealthChecker (verifies registry & DAG health)
        └── status.py                   # HealthReport schema and status definitions
```

---

## 3. Module Responsibilities

| Module | Core Responsibility | Non-Responsibilities (Explicitly Forbidden) |
| :--- | :--- | :--- |
| **`contracts/`** | Defines pure data representations, schemas, enums, and domain exception classes. Enforces structural validity. | Does NOT execute business logic, call databases, or import external services. |
| **`registry/`** | Loads and validates `models.json` (canonical) and maintains the in-memory registry of approved intelligence modules and capabilities. | Does NOT connect to model provider APIs, download weights, or store live credentials. |
| **`workflow/`** | Models Task DAGs, detects dependency cycles, validates inputs/outputs between connected nodes, and computes deterministic topological execution stages. | Does NOT execute task handlers or spawn OS worker processes. |
| **`engine/`** | Coordinates in-process task execution, dispatches tasks to registered handlers, manages timeouts via thread futures and monotonic deadlines, and enforces bounded retry arithmetic for transient resource errors (timeout retries strictly prohibited in R0). | Does NOT manage distributed task queues (no Celery/Redis) or bypass policy guards. |
| **`policy/`** | Evaluates whether a requested capability is permitted for the given context. Enforces default-deny rules and blocks shell/SQL execution. | Does NOT modify user roles or alter database ACL tables. |
| **`evaluation/`** | Records execution latency and outcomes; runs deterministic validation rubrics on task outputs; classifies errors into failure taxonomy. | Does NOT perform subjective LLM judge evaluations or train neural models. |
| **`health/`** | Evaluates engine readiness, confirms registry schema integrity, and generates structured diagnostic reports. | Does NOT mutate system state or expose internal credential details. |

---

## 4. Typed Interface Definitions and Data Flow

To ensure 100% offline compatibility, zero external C-extension risks across Python 3.11 and 3.14, and high execution speed, PIE R0 contracts are designed using Python's standard library `@dataclass(frozen=True)` and strict `typing` constructs:

### 4.1. Core Enums (`contracts/task.py`, `contracts/results.py`)

```python
from enum import Enum

class ProvenanceType(str, Enum):
    """Origin of data produced by a task."""
    OBSERVED = "observed"    # Deterministic measurement, regex extraction, direct parser output
    PREDICTED = "predicted"  # Output of statistical ML classifier or heuristic algorithm
    INFERRED = "inferred"    # Multi-factor algorithmic deduction or legacy baseline synthesis

class StepStatus(str, Enum):
    """Lifecycle state of an individual task step in a DAG."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"

class WorkflowStatus(str, Enum):
    """Consolidated lifecycle outcome of the entire workflow DAG."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"

class Capability(str, Enum):
    """Enumeration of authorized intelligence capabilities."""
    DOCUMENT_PARSING = "capability.document.parse"
    ATS_SCORING = "capability.resume.ats_score"
    KEYWORD_MATCHING = "capability.text.keyword_match"
    QUESTION_STRUCTURING = "capability.interview.question_structure"
    METRIC_COMPUTATION = "capability.analytics.compute_metrics"
    BASELINE_EVALUATION = "capability.legacy.baseline_eval"
```

### 4.2. Context & Task Contracts with Recursive Immutability (`contracts/context.py`, `contracts/task.py`)

To ensure deep recursive immutability using Python standard library constructs without external dependencies, all contract collections are recursively frozen into immutable standard library types (`types.MappingProxyType`, `tuple`, `frozenset`). Caller-owned mutable inputs are defensively copied to prevent mutation through retained references (aliasing protection), active call-stack recursion tracking detects genuine cycles while cleanly permitting shared-reference DAGs (diamond references), and duck typing is strictly rejected.

#### Supported-Value Contract for R0
To avoid vulnerabilities where arbitrary custom objects or mutable dataclasses are passed through, PIE enforces an explicit supported-value specification:
- **Primitives:** `str`, `int`, finite `float` (`math.isfinite(x)`: rejects `inf`, `-inf`, `nan`), `bool`, and `None`.
- **Identifiers & Enums:** `uuid.UUID` (serialized to `str`), and `enum.Enum` (serialized via declared `.value`).
- **Mappings:** `dict` and `MappingProxyType`. **Keys must be strings (`str`)**. Values are recursively frozen into `MappingProxyType`. Non-string keys raise `ContractViolationError`.
- **Sequences:** `list` and `tuple`. Elements are recursively frozen into `tuple`.
- **Internal Sets (`frozenset[str]`):** In R0, sets and frozensets are permitted **only for internal contract metadata** (e.g. `TaskDefinition.depends_on`) and **may contain only strings (`str`)**. Elements are frozen into `frozenset[str]`. Heterogeneous sets or sets containing non-string elements (e.g. `int`, `float`, objects) are strictly rejected with `ContractViolationError`.
  - **Payload Restriction:** Sets and frozensets are **strictly prohibited** in JSON-bound task payloads (`TaskInput.payload`, `TaskOutput.data`, `ExecutionResult.task_results`). JSON specifications lack a native set primitive; callers must supply ordered sequences (`list` or `tuple`). Passing sets/frozensets inside task payloads raises `ContractViolationError`.
- **Approved Contracts (`APPROVED_CONTRACT_TYPES`):** Nested contract validation strictly enforces **exact concrete-type membership**: `type(obj) in APPROVED_CONTRACT_TYPES`. The approved allowlist contains only the concrete R0 contract classes (`ExecutionContext`, `TaskInput`, `TaskOutput`, `TaskResult`, `TaskDefinition`, `WorkflowDefinition`, `ExecutionResult`).
  - **Rejection of Unregistered Subclasses:** Subclasses of `BaseContract` that are not explicitly registered in `APPROVED_CONTRACT_TYPES` are strictly rejected with `ContractViolationError`.
  - **Rejection of Duck Typing:** Checking `hasattr(obj, "to_dict")` is strictly prohibited.
  - **Circular Import Prevention:** Contract classes register themselves via a `@register_contract` decorator defined in `contracts/base.py`, establishing a strictly acyclic import DAG where `base.py` never imports concrete contract modules.
- **Recursive Validation on Serialization:** When an approved contract is unfrozen, its `.to_dict()` output is itself recursively passed through `unfreeze_to_dict()` to guarantee that internal fields adhere to the supported-value contract and cannot introduce unsupported types, non-finite floats, or cyclic references.
- **Unsupported Types:** Arbitrary custom objects, mutable class instances, generators, lambdas, unregistered `BaseContract` subclasses, and non-contract dataclasses are strictly rejected with `ContractViolationError`.
- **Cycle Detection & Aliasing Semantics:** Recursive traversal tracks the active call stack via `active_path = set()` using `id(obj)` with `try...finally`.
  - An object ID is added upon entering traversal and removed upon leaving (including exceptional exits).
  - Genuine cycles ($A \to B \to A$ or self-references) are rejected with `ContractViolationError`.
  - Shared-reference DAG structures (diamond graphs: $A \to [B, C]$ where both $B$ and $C$ reference container $D$) are cleanly permitted without false positives.
  - Mutable input containers (`dict`, `list`, `set`) are defensively copied into fresh immutable wrappers, guaranteeing that caller modifications to original inputs cannot alter contract data.
- **Strict Subclass Type-Check Ordering:** In Python, `bool` is a subclass of `int` (`issubclass(bool, int) is True`), and `IntEnum` is a subclass of `int` (`issubclass(IntEnum, int) is True`). To prevent `bool` and `IntEnum` instances from being mistakenly evaluated as primitive integers, type evaluations must strictly check `bool` and `Enum` before `int`.
- **Deterministic Serialization Contract:** All contracts implement an explicit `.to_dict()` method powered by `unfreeze_to_dict()`. Internal string sets are deterministically serialized via standard lexicographical string sorting (`sorted(obj)`), producing a clean `list[str]` with zero collision risk. **`dataclasses.asdict()` is strictly avoided**.

```python
import math
import uuid
import time
from enum import Enum
from types import MappingProxyType
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, Sequence, Set


class BaseContract:
    """
    Abstract base class for all approved PIE contracts.
    Subclasses must be explicitly registered via @register_contract to be accepted.
    Unregistered subclasses of BaseContract are strictly rejected.
    """
    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses of BaseContract must implement .to_dict()")


_APPROVED_CONTRACT_CLASSES: Set[type] = set()

def register_contract(cls: type) -> type:
    """
    Decorator that registers a concrete contract class in the approved contract allowlist.
    Avoids circular imports: concrete contract modules import register_contract from base.py.
    """
    _APPROVED_CONTRACT_CLASSES.add(cls)
    return cls

def is_approved_contract(obj: Any) -> bool:
    """
    Enforces exact concrete-type membership: type(obj) in APPROVED_CONTRACT_TYPES.
    Rejects unregistered classes even if they inherit from BaseContract.
    """
    return type(obj) in _APPROVED_CONTRACT_CLASSES

def get_approved_contract_types() -> Tuple[type, ...]:
    """Returns the immutable tuple of all registered approved contract classes."""
    return tuple(_APPROVED_CONTRACT_CLASSES)


def freeze_immutable(
    obj: Any,
    active_path: Optional[Set[int]] = None,
    allow_sets: bool = True,
) -> Any:
    """
    Recursively and defensively freezes supported data structures into immutable standard-library representations.
    Rejects unsupported types, non-finite floats, non-string mapping keys, unregistered contract types, and genuine cycles.
    Permits shared-reference DAGs (diamond references) via active call-stack tracking.
    """
    if active_path is None:
        active_path = set()

    # ── STRICT TYPE CHECK ORDERING (bool and Enum MUST precede int) ──
    # 1. NoneType
    if obj is None:
        return None

    # 2. Boolean (must precede int because issubclass(bool, int) is True)
    if isinstance(obj, bool):
        return obj

    # 3. Enum (must precede int because issubclass(IntEnum, int) is True)
    if isinstance(obj, Enum):
        return obj

    # 4. Pure Integer
    if isinstance(obj, int):
        return obj

    # 5. Finite Float (strictly rejects inf, -inf, nan)
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ContractViolationError(f"Non-finite float value '{obj}' is rejected by contract.")
        return obj

    # 6. String
    if isinstance(obj, str):
        return obj

    # 7. UUID
    if isinstance(obj, uuid.UUID):
        return obj

    # 8. Approved Contract (exact concrete type membership; unregistered subclasses rejected)
    if is_approved_contract(obj):
        return obj

    # ── CONTAINER RECURSION WITH CALL-STACK CYCLE TRACKING ──
    obj_id = id(obj)
    if obj_id in active_path:
        raise ContractViolationError(f"Cyclic reference detected in contract data (container id: {obj_id})")

    active_path.add(obj_id)
    try:
        # 9. Mappings (keys must be strings, defensively copied into MappingProxyType)
        if isinstance(obj, (dict, MappingProxyType)):
            frozen_dict = {}
            for k, v in obj.items():
                if not isinstance(k, str):
                    raise ContractViolationError(
                        f"Mapping keys must be strings; received key '{k}' of type {type(k).__name__}"
                    )
                frozen_dict[k] = freeze_immutable(v, active_path, allow_sets=allow_sets)
            return MappingProxyType(frozen_dict)

        # 10. Sequences (defensively copied into immutable tuple)
        if isinstance(obj, (list, tuple)):
            return tuple(freeze_immutable(item, active_path, allow_sets=allow_sets) for item in obj)

        # 11. Sets (internal contract metadata only: strictly string-only, frozen into frozenset[str])
        if isinstance(obj, (set, frozenset)):
            if not allow_sets:
                raise ContractViolationError(
                    "Sets and frozensets are prohibited in JSON-bound task payloads. Use ordered lists or tuples instead."
                )
            for item in obj:
                if not isinstance(item, str):
                    raise ContractViolationError(
                        f"Internal set elements must be strings (str); found '{item}' of type {type(item).__name__}."
                    )
            return frozenset(sorted(obj))

        # 12. Unsupported types rejected (unregistered BaseContract subclasses or duck-typed objects fail here)
        raise ContractViolationError(
            f"Unsupported type '{type(obj).__name__}' cannot be made immutable. "
            "Only primitives (str, int, finite float, bool, None), UUIDs, Enums, approved contract types, "
            "and nested dicts/lists/string-frozensets of these types are permitted in task contracts."
        )
    finally:
        active_path.remove(obj_id)


def unfreeze_to_dict(obj: Any, active_path: Optional[Set[int]] = None) -> Any:
    """
    Recursively unfreezes immutable structures back into native JSON-compatible Python dicts and lists.
    Guarantees deterministic serialization:
    - String sets/frozensets are deterministically sorted via standard lexicographical order.
    - UUIDs are converted to str.
    - Enums are converted to their declared .value.
    - Approved contract objects have their .to_dict() output recursively validated and unfrozen.
    - Non-finite floats are strictly rejected.
    """
    if active_path is None:
        active_path = set()

    # ── STRICT TYPE CHECK ORDERING (bool and Enum MUST precede int) ──
    # 1. NoneType
    if obj is None:
        return None

    # 2. Boolean (must precede int)
    if isinstance(obj, bool):
        return obj

    # 3. Enum (must precede int; extracts .value)
    if isinstance(obj, Enum):
        return unfreeze_to_dict(obj.value, active_path)

    # 4. Pure Integer
    if isinstance(obj, int):
        return obj

    # 5. Finite Float
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ContractViolationError(f"Non-finite float value '{obj}' cannot be serialized.")
        return obj

    # 6. String
    if isinstance(obj, str):
        return obj

    # 7. UUID
    if isinstance(obj, uuid.UUID):
        return str(obj)

    # ── CONTAINER / CONTRACT RECURSION WITH CALL-STACK CYCLE TRACKING ──
    obj_id = id(obj)
    if obj_id in active_path:
        raise ContractViolationError("Cyclic reference detected during serialization.")

    active_path.add(obj_id)
    try:
        # 8. Approved Contract (recursively validates and unfreezes .to_dict() output)
        if is_approved_contract(obj):
            raw_dict = obj.to_dict()
            return unfreeze_to_dict(raw_dict, active_path)

        # 9. Mappings
        if isinstance(obj, (dict, MappingProxyType)):
            return {str(k): unfreeze_to_dict(v, active_path) for k, v in obj.items()}

        # 10. Sequences
        if isinstance(obj, (list, tuple)):
            return [unfreeze_to_dict(item, active_path) for item in obj]

        # 11. Sets/Frozensets (Strictly string elements, sorted lexicographically)
        if isinstance(obj, (set, frozenset)):
            return sorted(obj)

        raise ContractViolationError(f"Cannot serialize unsupported type '{type(obj).__name__}' to JSON.")
    finally:
        active_path.remove(obj_id)


@register_contract
@dataclass(frozen=True)
class ExecutionContext(BaseContract):
    """Immutable contextual metadata propagated across workflow execution (recursively frozen, monotonic deadline)."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    deadline_mono: Optional[float] = None
    timeout_seconds: Optional[float] = None
    environment: str = "development"
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __init__(
        self,
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        deadline_mono: Optional[float] = None,
        environment: str = "development",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        object.__setattr__(self, "trace_id", trace_id or str(uuid.uuid4()))
        object.__setattr__(self, "request_id", request_id or str(uuid.uuid4()))
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "session_id", session_id)

        # Monotonic deadline calculation (immune to NTP steps or system clock adjustments)
        if deadline_mono is not None:
            if isinstance(deadline_mono, bool):
                raise ContractViolationError("deadline_mono cannot be a boolean.")
            try:
                eff_deadline = float(deadline_mono)
            except (ValueError, TypeError):
                raise ContractViolationError(
                    f"deadline_mono must be a valid numeric float, got {type(deadline_mono).__name__}"
                )
            if eff_deadline < 0 or not math.isfinite(eff_deadline):
                raise ContractViolationError("deadline_mono must be non-negative and finite.")
        elif timeout_seconds is not None:
            if isinstance(timeout_seconds, bool):
                raise ContractViolationError("timeout_seconds cannot be a boolean.")
            try:
                tout = float(timeout_seconds)
            except (ValueError, TypeError):
                raise ContractViolationError(
                    f"timeout_seconds must be a valid numeric float, got {type(timeout_seconds).__name__}"
                )
            if not (0.0 < tout <= 300.0) or not math.isfinite(tout):
                raise ContractViolationError(
                    f"timeout_seconds must be in range (0.0, 300.0] and finite, got {tout}"
                )
            eff_deadline = time.monotonic() + tout
        else:
            eff_deadline = None

        object.__setattr__(self, "deadline_mono", eff_deadline)
        object.__setattr__(
            self,
            "timeout_seconds",
            tout if timeout_seconds is not None else None,
        )
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "metadata", freeze_immutable(metadata or {}))

    def is_expired(self) -> bool:
        if self.deadline_mono is None:
            return False
        return time.monotonic() > self.deadline_mono

    def remaining_seconds(self) -> Optional[float]:
        if self.deadline_mono is None:
            return None
        return max(0.0, self.deadline_mono - time.monotonic())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timeout_seconds": self.timeout_seconds,
            "remaining_seconds": self.remaining_seconds(),
            "environment": self.environment,
            "metadata": unfreeze_to_dict(self.metadata),
        }


@register_contract
@dataclass(frozen=True)
class TaskInput(BaseContract):
    """Typed input payload delivered to a task handler (recursively frozen & aliasing-safe)."""
    capability: Capability
    payload: MappingProxyType
    context: ExecutionContext
    config_overrides: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __init__(
        self,
        capability: Capability,
        payload: Dict[str, Any],
        context: ExecutionContext,
        config_overrides: Optional[Dict[str, Any]] = None,
    ):
        object.__setattr__(self, "capability", capability)
        # JSON-bound payload disallows sets/frozensets; callers must supply ordered sequences
        object.__setattr__(self, "payload", freeze_immutable(payload, allow_sets=False))
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "config_overrides", freeze_immutable(config_overrides or {}, allow_sets=False))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability.value,
            "payload": unfreeze_to_dict(self.payload),
            "context": self.context.to_dict(),
            "config_overrides": unfreeze_to_dict(self.config_overrides),
        }


@register_contract
@dataclass(frozen=True)
class TaskOutput(BaseContract):
    """Typed result returned by a task handler (recursively frozen)."""
    data: MappingProxyType
    provenance: ProvenanceType
    confidence: Optional[float] = None
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    def __init__(
        self,
        data: Dict[str, Any],
        provenance: ProvenanceType,
        confidence: Optional[float] = None,
        warnings: Optional[Sequence[str]] = None,
    ):
        # JSON-bound data disallows sets/frozensets; callers must supply ordered sequences
        object.__setattr__(self, "data", freeze_immutable(data, allow_sets=False))
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "warnings", tuple(str(w) for w in (warnings or ())))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": unfreeze_to_dict(self.data),
            "provenance": self.provenance.value,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }
```

### 4.3. Execution Result & Error Contracts (`contracts/results.py`, `contracts/exceptions.py`)

```python
@register_contract
@dataclass(frozen=True)
class TaskResult(BaseContract):
    """Structured execution outcome of a single task in a DAG."""
    task_id: str
    capability: Capability
    status: StepStatus
    output: Optional[TaskOutput] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    latency_ms: float = 0.0
    retry_count: int = 0
    execution_token: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "capability": self.capability.value,
            "status": self.status.value,
            "output": self.output.to_dict() if self.output else None,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "execution_token": self.execution_token,
        }

@register_contract
@dataclass(frozen=True)
class ExecutionResult(BaseContract):
    """Consolidated outcome of an entire workflow execution."""
    trace_id: str
    workflow_id: str
    status: WorkflowStatus
    task_results: MappingProxyType  # Maps task_id -> TaskResult
    total_latency_ms: float
    errors: Tuple[str, ...] = field(default_factory=tuple)

    def __init__(
        self,
        trace_id: str,
        workflow_id: str,
        status: WorkflowStatus,
        task_results: Dict[str, TaskResult],
        total_latency_ms: float,
        errors: Optional[Sequence[str]] = None,
    ):
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "workflow_id", workflow_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "task_results", freeze_immutable(task_results, allow_sets=False))
        object.__setattr__(self, "total_latency_ms", total_latency_ms)
        object.__setattr__(self, "errors", tuple(errors or ()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "task_results": unfreeze_to_dict(self.task_results),
            "total_latency_ms": self.total_latency_ms,
            "errors": list(self.errors),
        }

# ── DOMAIN EXCEPTION HIERARCHY (NO SHADOW OF PYTHON BUILT-INS) ──
class PIEException(Exception):
    """Base exception for all PIE domain errors."""
    def __init__(self, message: str, code: str = "PIE_INTERNAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code

class ContractViolationError(PIEException):
    """Raised when payload fails contract validation."""
    def __init__(self, message: str):
        super().__init__(message, "CONTRACT_VIOLATION")

class PolicyViolationError(PIEException):
    """Raised when an operation violates security policy (e.g. raw SQL/shell)."""
    def __init__(self, message: str):
        super().__init__(message, "POLICY_VIOLATION")

class UnauthorizedCapabilityError(PIEException):
    """Raised when a task requests a capability not granted to the caller."""
    def __init__(self, capability: str):
        super().__init__(f"Capability '{capability}' is unauthorized.", "UNAUTHORIZED_CAPABILITY")

class WorkflowCycleError(PIEException):
    """Raised when a cycle is detected in a TaskDAG."""
    def __init__(self, cycle_path: Sequence[str]):
        super().__init__(f"Cyclic dependency detected: {' -> '.join(cycle_path)}", "WORKFLOW_CYCLE")

class TaskTimeoutError(PIEException):
    """Raised when task exceeds its configured execution deadline."""
    def __init__(self, task_id: str, timeout_sec: float):
        super().__init__(f"Task '{task_id}' exceeded timeout of {timeout_sec}s", "TASK_TIMEOUT")

class RegistryModuleNotFoundError(PIEException):
    """Raised when an intelligence module is missing from ModuleRegistry (avoids shadowing built-in ModuleNotFoundError)."""
    def __init__(self, module_id: str):
        super().__init__(f"Module '{module_id}' not found in registry.", "MODULE_NOT_FOUND")

class RegistryModelNotFoundError(PIEException):
    """Raised when a model identifier is missing from ModelRegistry."""
    def __init__(self, model_id: str):
        super().__init__(f"Model '{model_id}' not found in registry.", "MODEL_NOT_FOUND")
```

### 4.4. End-to-End Data Flow

```
                      Client / Application Request
                                   │
                                   ▼
                         ExecutionContext
               [trace_id, request_id, user_id, deadline]
                                   │
                                   ▼
                            TaskDAG Builder
            [Tasks A, B, C, D with explicit dependency edges]
                                   │
                                   ▼
                         DAG Validation Stage
            [Graph cycle check via DFS; orphan node check]
                                   │
                                   ▼
                          Policy Guard Check
           [Verifies capabilities against default-deny policy]
                                   │
                                   ▼
                        Stage-by-Stage Dispatch
         ┌─────────────────────────────────────────────────────┐
         │ Stage 0: Root Tasks (Executed concurrently)        │
         │          Task A (e.g. Document Parser)              │
         └─────────────────────────┬───────────────────────────┘
                                   ▼
         ┌─────────────────────────────────────────────────────┐
         │ Stage 1: Dependent Tasks (Concurrently after A)     │
         │          Task B (Skill Extractor)                   │
         │          Task C (Section Classifier)                │
         └─────────────────────────┬───────────────────────────┘
                                   ▼
         ┌─────────────────────────────────────────────────────┐
         │ Stage 2: Final Synthesizer                          │
         │          Task D (ATS Scorer)                        │
         └─────────────────────────┬───────────────────────────┘
                                   │
                                   ▼
                        Deterministic Evaluator
        [Validates schema bounds, confidence limits, provenance]
                                   │
                                   ▼
                            ExecutionResult
           [Consolidated typed result with latency & metrics]
```

---

## 5. Workflow DAG Execution Lifecycle

A workflow in PIE is defined as a Directed Acyclic Graph (DAG) of discrete tasks.

### 5.1. Task Definition (`contracts/task.py`)
```python
@register_contract
@dataclass(frozen=True)
class TaskDefinition(BaseContract):
    """Static declarative definition of a single task in a workflow DAG (recursively frozen)."""
    task_id: str
    capability: Capability
    handler: str                              # Registered module/handler identifier
    depends_on: Tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 5.0              # Task-level timeout cap (max 15.0s)
    max_retries: int = 0                      # Default: 0 (bounded max: 2; transient non-timeout errors only)
    backoff_factor: float = 0.5
    is_idempotent: bool = False               # Future-facing metadata; required True for transient retries
    retry_on_timeout: bool = False            # Strictly False in R0: timeout retries prohibited engine-wide

    def __init__(
        self,
        task_id: str,
        capability: Capability,
        handler: str,
        depends_on: Optional[Sequence[str]] = None,
        timeout_seconds: float = 5.0,
        max_retries: int = 0,
        backoff_factor: float = 0.5,
        is_idempotent: bool = False,
        retry_on_timeout: bool = False,
    ):
        if not isinstance(capability, Capability):
            raise ContractViolationError(
                f"capability must be an instance of Capability enum, got {type(capability).__name__}"
            )
        if not task_id or not isinstance(task_id, str):
            raise ContractViolationError("task_id must be a non-empty string.")
        if not handler or not isinstance(handler, str):
            raise ContractViolationError("handler must be a non-empty string.")

        deps = depends_on or ()
        for dep in deps:
            if not isinstance(dep, str):
                raise ContractViolationError(
                    f"depends_on elements must be strings, got {type(dep).__name__}"
                )

        if isinstance(timeout_seconds, bool):
            raise ContractViolationError("timeout_seconds cannot be a boolean.")
        try:
            tout = float(timeout_seconds)
        except (ValueError, TypeError):
            raise ContractViolationError(
                f"timeout_seconds must be a valid numeric float, got {type(timeout_seconds).__name__}"
            )
        if tout <= 0 or not math.isfinite(tout):
            raise ContractViolationError(
                f"timeout_seconds must be positive and finite, got {tout}"
            )

        if isinstance(max_retries, bool):
            raise ContractViolationError("max_retries cannot be a boolean.")
        try:
            retries = int(max_retries)
        except (ValueError, TypeError):
            raise ContractViolationError(
                f"max_retries must be a valid integer, got {type(max_retries).__name__}"
            )

        if isinstance(backoff_factor, bool):
            raise ContractViolationError("backoff_factor cannot be a boolean.")
        try:
            backoff = float(backoff_factor)
        except (ValueError, TypeError):
            raise ContractViolationError(
                f"backoff_factor must be a valid numeric float, got {type(backoff_factor).__name__}"
            )
        if backoff <= 0 or not math.isfinite(backoff):
            raise ContractViolationError(
                f"backoff_factor must be positive and finite, got {backoff}"
            )

        object.__setattr__(self, "task_id", str(task_id))
        object.__setattr__(self, "capability", capability)
        object.__setattr__(self, "handler", str(handler))
        object.__setattr__(self, "depends_on", tuple(str(d) for d in deps))
        object.__setattr__(self, "timeout_seconds", min(tout, 15.0))
        object.__setattr__(self, "max_retries", max(0, min(retries, 2)))
        object.__setattr__(self, "backoff_factor", max(0.1, backoff))
        object.__setattr__(self, "is_idempotent", bool(is_idempotent))
        # Strictly forced to False in R0: timeout retries are prohibited engine-wide
        object.__setattr__(self, "retry_on_timeout", False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "capability": self.capability.value,
            "handler": self.handler,
            "depends_on": list(self.depends_on),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "backoff_factor": self.backoff_factor,
            "is_idempotent": self.is_idempotent,
            "retry_on_timeout": self.retry_on_timeout,
        }
```

### 5.2. Workflow Definition & Timeout Hierarchy (`contracts/workflow.py`)

A `WorkflowDefinition` formalizes the static declaration of an entire task DAG. It encapsulates all `TaskDefinition` instances, enforces key-matching invariants, and applies orchestration-level timeout limits.

```python
@register_contract
@dataclass(frozen=True)
class WorkflowDefinition(BaseContract):
    """Static declarative definition of a full workflow DAG composed of TaskDefinitions."""
    workflow_id: str
    tasks: MappingProxyType  # Maps task_id -> TaskDefinition
    timeout_seconds: float = 30.0

    def __init__(
        self,
        workflow_id: str,
        tasks: Dict[str, TaskDefinition],
        timeout_seconds: float = 30.0,
    ):
        if not workflow_id or not isinstance(workflow_id, str):
            raise ContractViolationError("workflow_id must be a non-empty string.")
        if not isinstance(tasks, (dict, MappingProxyType)) or not tasks:
            raise ContractViolationError("tasks must be a non-empty mapping of task_id -> TaskDefinition.")

        for tid, tdef in tasks.items():
            if not isinstance(tid, str):
                raise ContractViolationError(f"Task mapping key must be str, got {type(tid).__name__}")
            if type(tdef) is not TaskDefinition:
                raise ContractViolationError(
                    f"Task mapping value for '{tid}' must be an exact TaskDefinition instance, got {type(tdef).__name__}"
                )
            if tid != tdef.task_id:
                raise ContractViolationError(
                    f"Task mapping key '{tid}' does not match TaskDefinition.task_id '{tdef.task_id}'"
                )

        if isinstance(timeout_seconds, bool):
            raise ContractViolationError("timeout_seconds cannot be a boolean.")
        try:
            tout = float(timeout_seconds)
        except (ValueError, TypeError):
            raise ContractViolationError(
                f"timeout_seconds must be a valid numeric float, got {type(timeout_seconds).__name__}"
            )
        if tout <= 0 or not math.isfinite(tout):
            raise ContractViolationError(
                f"timeout_seconds must be positive and finite, got {tout}"
            )

        object.__setattr__(self, "workflow_id", str(workflow_id))
        object.__setattr__(self, "tasks", freeze_immutable(tasks, allow_sets=False))
        object.__setattr__(self, "timeout_seconds", min(tout, 60.0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "timeout_seconds": self.timeout_seconds,
        }
```

#### The Three-Level Timeout Hierarchy
PIE establishes a strict, three-tier timeout hierarchy to safeguard workflow execution across envelopes, graphs, and task handlers:

1. **Level 1 — Context Envelope Timeout (`ExecutionContext.timeout_seconds`)**:
   - **Scope:** Outer envelope timeout covering the entire user request or API session.
   - **Bounds:** Strictly $(0.0, 300.0]\text{s}$; non-positive, non-finite, and boolean values are rejected with `ContractViolationError`.
   - **Mechanism:** Governs monotonic deadline tracking (`deadline_mono = time.monotonic() + timeout_seconds`), immune to wall-clock shifts and NTP adjustments.

2. **Level 2 — Workflow Orchestration Timeout (`WorkflowDefinition.timeout_seconds`)**:
   - **Scope:** Orchestration-level timeout for coordinating and completing the entire DAG across all stages.
   - **Bounds:** Constructor default is $30.0\text{s}$; clamped to a hard maximum cap of $60.0\text{s}$ via `min(tout, 60.0)`.
   - **Validation:** Must be positive and finite. Booleans and non-numeric values are rejected with `ContractViolationError`.
   - **Mechanism:** If accumulated workflow latency exceeds this limit, remaining stages are aborted and unexecuted tasks are marked as `SKIPPED` or `TIMED_OUT`.

3. **Level 3 — Task Handler Execution Timeout (`TaskDefinition.timeout_seconds`)**:
   - **Scope:** Execution timeout dedicated to an individual task handler inside a worker thread.
   - **Bounds:** Constructor default is $5.0\text{s}$; clamped to a hard maximum cap of $15.0\text{s}$ via `min(tout, 15.0)`.
   - **Validation:** Must be positive and finite. Booleans and non-numeric values are rejected with `ContractViolationError`.

#### Dynamic Effective Task Deadline Relationship
To prevent runaway execution where an individual task timeout exceeds the remaining workflow or context window, the coordinator enforces the following invariant:

$$\text{effective\_task\_deadline} = \min(\text{task\_timeout}, \text{remaining\_workflow\_timeout}, \text{remaining\_context\_timeout})$$

Under this invariant, an individual task is strictly bounded by the tightest available time budget. No task can execute longer than its own handler timeout ($15.0\text{s}$ max) or outlive the workflow ($60.0\text{s}$ max) or context ($300.0\text{s}$ max).

### 5.3. Cycle Detection via 3-Color Depth-First Search (`workflow/validator.py`)
To prevent infinite recursion and deadlocks, the DAG topology is validated prior to execution using the standard **Three-Color Graph Algorithm**:
- **White (0):** Unvisited node.
- **Gray (1):** Node currently in the recursive call stack (active branch).
- **Black (2):** Node completely evaluated and closed.

If a DFS traversal encounters a **Gray** node, a back-edge exists, proving a cycle. The validator immediately raises `WorkflowCycleError` with the exact circular path.

```python
# Topological Validation Pseudocode
def validate_dag(tasks: Dict[str, TaskDefinition]) -> None:
    color = {tid: 0 for tid in tasks}
    path = []

    def dfs(node_id: str):
        color[node_id] = 1 # Gray
        path.append(node_id)
        for dep_id in tasks[node_id].depends_on:
            if dep_id not in tasks:
                raise ContractViolationError(f"Task '{node_id}' depends on missing task '{dep_id}'")
            if color[dep_id] == 1: # Encountered Gray node -> Cycle
                cycle = path[path.index(dep_id):] + [dep_id]
                raise WorkflowCycleError(cycle)
            if color[dep_id] == 0:
                dfs(dep_id)
        path.pop()
        color[node_id] = 2 # Black

    for tid in tasks:
        if color[tid] == 0:
            dfs(tid)
```

### 5.4. Deterministic Topological Stage Scheduling (`workflow/ordering.py`)
Tasks are partitioned into discrete **Execution Stages** using Kahn's algorithm or level-order topological sorting:
- **Stage 0:** All tasks with 0 dependencies.
- **Stage 1:** Tasks whose dependencies are all satisfied by Stage 0.
- **Stage N:** Tasks whose dependencies are all satisfied by Stages 0 through N-1.

**Execution Rule:**
- Tasks within the same stage are mutually independent and can be executed concurrently in a thread pool (`ThreadPoolExecutor(max_workers=4)`).
- Stages execute in strict sequential order (Stage 0 -> Stage 1 -> Stage 2).
- If any task fails and cannot be recovered via bounded retries, dependent descendant tasks in subsequent stages are marked as `SKIPPED`.

---

## 6. Registry Schema and Validation Strategy

### 6.1. Model Registry Architecture & Package Structure

In PrepAI PIE R0, the Model Registry provides a deterministic, validated, fail-closed source of model metadata for intelligence tasks. The architecture strictly enforces a boundary between declarative model descriptions and executable task handlers:

- **`ModelRegistry` (Declarative Metadata):** Ingests and validates the static model catalog (`models.json`), enforcing schema integrity, capability compatibility, lifecycle states (e.g. `production` vs `baseline_only`), and credential-free declarative configuration. It performs zero network calls, contains zero credentials, does not load filesystem paths, and never executes model code.
- **`ModuleRegistry` (Executable Handlers):** Statically registers pure Python task handlers in trusted application code. Task handlers map directly to `Capability` contracts and execute deterministic algorithms or baseline model invocations. Handlers are linked via code-level registrations, never by dynamically importing module strings from JSON manifests.

#### Canonical Provider Identifiers:
The registry defines one canonical provider identifier for each supported compute provider in R0:
1. **`internal_deterministic`**: Pure in-process Python algorithms running synchronously in application memory without network, sockets, or subprocesses.
   - *Resolution Note:* Replaces ambiguous terms like `local_procedural` to clearly distinguish in-process code from local external daemons.
2. **`ollama`**: Local loopback HTTP runner (`127.0.0.1:11434`) running external open-weight LLMs (e.g. Llama 3 8B). Strictly `baseline_only`.
3. **`gemini`**: External Google Gemini cloud API (via Google GenAI SDK). Strictly `baseline_only`.
   - *Resolution Note:* Replaces `google_genai` to align directly with backend configuration (`GEMINI_MODEL`, `GEMINI_API_KEY`) and existing service code (`GeminiService.provider = "gemini"`).

**Runtime Availability Disclaimer:** Declaring a provider identifier in `models.json` documents metadata compatibility; it does NOT guarantee or claim that an external provider (such as Ollama or Gemini) is installed, reachable, or configured with valid credentials at runtime.

The package structure under `backend/pie/registry/` is strictly modular:

```
backend/pie/
├── __init__.py
├── contracts/                        # Frozen core contracts (Step 3B.1)
└── registry/                         # Model Registry & Manifest Layer (Step 3B.2)
    ├── __init__.py                   # Public exports: ModelRegistry, ModelMetadata, ModelStatus, etc.
    ├── models.json                   # Canonical declarative model metadata manifest (5 baseline entries)
    ├── schema.py                     # Strongly-typed immutable dataclasses (ModelMetadata, Constraints, etc.)
    ├── loader.py                     # Strict, fail-closed JSON manifest loader and recursive security validator
    ├── registry.py                   # In-memory query store, immutable snapshot cache, and capability lookup
    └── exceptions.py                 # Registry-specific domain exceptions (inheriting from PIEException)
```

### 6.2. Capability Enum Invariant & Disambiguation

Capabilities in PIE represent statically authorized units of intelligence work. The registry strictly enforces exact compatibility with the frozen `Capability` enum defined in `backend/pie/contracts/task.py`:

```python
class Capability(str, Enum):
    """Enumeration of all statically authorized capabilities within PIE."""
    DOCUMENT_PARSING = "capability.document.parse"
    ATS_SCORING = "capability.resume.ats_score"
    KEYWORD_MATCHING = "capability.text.keyword_match"
    QUESTION_STRUCTURING = "capability.interview.question_structure"
    METRIC_COMPUTATION = "capability.analytics.compute_metrics"
    BASELINE_EVALUATION = "capability.legacy.baseline_eval"
```

#### Exact Member Names vs. Serialized String Values:

| Enum Member Name | Serialized String Value (Stored in `models.json`) | Description | Initial Manifest Production Status |
| :--- | :--- | :--- | :---: |
| `Capability.DOCUMENT_PARSING` | `"capability.document.parse"` | Extract raw text and structural layout from resume documents. | **Unassigned** (Fails closed in R0) |
| `Capability.ATS_SCORING` | `"capability.resume.ats_score"` | Score candidate resumes against job descriptions via ATS criteria. | `deterministic-ats-regex-v1` |
| `Capability.KEYWORD_MATCHING` | `"capability.text.keyword_match"` | Identify and extract technical skills from candidate text. | `deterministic-ats-regex-v1` |
| `Capability.QUESTION_STRUCTURING` | `"capability.interview.question_structure"` | Procedurally assemble calibrated interview question blueprints. | `deterministic-question-matrix-v1` |
| `Capability.METRIC_COMPUTATION` | `"capability.analytics.compute_metrics"` | Compute quantified candidate metrics (fluff counts, match ratios). | `deterministic-metric-computer-v1` |
| `Capability.BASELINE_EVALUATION` | `"capability.legacy.baseline_eval"` | Reference baseline evaluation using external LLMs (`baseline_only`). | Baseline comparison only |

**Validation Invariant:** The manifest stores exclusively the **serialized string values**. The registry loader validates that every declared capability string is an exact member of `{c.value for c in Capability}`. Unknown capability strings or member names passed as strings (e.g. `"DOCUMENT_PARSING"`) trigger immediate load-time rejection with `UnknownCapabilityError`.

### 6.3. Canonical Manifest JSON Schema (`models.json`)

The canonical model manifest is stored as a single, static JSON document at `backend/pie/registry/models.json`. It is parsed using Python's standard library `json` module (maintaining the zero-new-dependency invariant).

#### Envelope Schema (No Decorative Timestamps):
In R0, loading is 100% synchronous, offline, and in-memory. The engine never evaluates expiry dates, schedules background refreshes, or tracks timestamp skew. To prevent unmaintained metadata and git churn, decorative timestamps (`created_at`, `updated_at`) are removed. The envelope contains exclusively the schema version and model catalog:

```json
{
  "manifest_version": "1.0.0",
  "models": [ ... ]
}
```

#### Timeout Authority & Elimination of Model-Level Timeouts:
> [!IMPORTANT]
> **Timeout Hierarchy Authority:** Execution timeouts in PIE are governed strictly and exclusively by the frozen task execution contracts:
> - `TaskDefinition.timeout_seconds`: Task execution deadline, default `10.0s`, strictly bounded by `(0.0, 15.0]`.
> - `ExecutionContext.timeout_seconds`: End-to-end workflow execution deadline, default `30.0s`, strictly bounded by `(0.0, 300.0]`.
>
> In R0, `models.json` **intentionally omits `timeout_seconds`**. Model metadata represents static capability and structural constraints, not execution deadlines. Introducing a separate model-level execution timeout would conflict with the frozen `TaskDefinition` hierarchy, risk passing incompatible baseline latencies (e.g. 30s or 60s) into the 15s task ceiling, and violate the principle of single authority. All production task execution respects the frozen contract's timeout hierarchy.

#### Complete Model Schema Specification:

```json
{
  "model_id": "string (unique slug, pattern ^[a-z0-9][a-z0-9-_]{2,63}$)",
  "name": "string (display name, 3..100 characters)",
  "model_type": "string (enum: heuristic | classifier | procedural_generator | statistical_ml | llm_external)",
  "provider": "string (enum: internal_deterministic | ollama | gemini)",
  "capabilities": ["string (exact Capability serialized value)"],
  "input_modalities": ["string (enum: text | structured_data)"],
  "output_modalities": ["string (enum: text | json | structured_data)"],
  "version": "string (entry/algorithm revision string, e.g. 1.0.0)",
  "upstream_version": "string | null (optional vendor model version, e.g. 2026.1)",
  "status": "string (enum: production | evaluation | development | deprecated | baseline_only)",
  "provenance": "string (enum: observed | predicted | inferred)",
  "constraints": {
    "max_input_length": 50000,
    "max_output_length": 10000,
    "requires_network": false,
    "requires_gpu": false,
    "deterministic": true
  },
  "configuration": {},
  "metadata": {
    "source_reference": "ml/nlp/resume_engine.py",
    "description": "Descriptive documentation string."
  }
}
```

#### Field-Level Semantic Rules:

1. **`model_id` (str, Required):** Globally unique lowercase identifier matching `^[a-z0-9][a-z0-9-_]{2,63}$`. Duplicates raise `DuplicateModelIdError`.
2. **`name` (str, Required):** Human-readable display label (3 to 100 characters).
3. **`model_type` (str, Required):** Algorithmic paradigm:
   - `heuristic`: Rule-based or procedural scoring/matching algorithm.
   - `classifier`: Statistical or taxonomy-based discrete classifier.
   - `procedural_generator`: Algorithmic content generator (e.g. structured question synthesis).
   - `statistical_ml`: In-process statistical machine learning model (e.g. scikit-learn).
   - `llm_external`: External Large Language Model accessed via loopback or API (strictly `baseline_only` in R0).
4. **`provider` (str, Required):** Compute provider identifier:
   - `internal_deterministic`: Pure in-process Python algorithms without subprocesses or sockets.
   - `ollama`: Local loopback HTTP runner (`127.0.0.1:11434`).
   - `gemini`: External Google Gemini API.
5. **`capabilities` (List[str], Required):** Non-empty list of supported capability strings matching `{c.value for c in Capability}`.
6. **`input_modalities` & `output_modalities` (List[str], Required):** Supported payload modalities (`text`, `structured_data`, `json`).
7. **Version Disambiguation:**
   - `manifest_version` (top-level): Schema format specification version of the JSON manifest document (e.g. `"1.0.0"`).
   - `version` (per-model): Registry entry version and algorithm implementation revision in this repository (e.g. `"1.0.0"`).
   - `upstream_version` (per-model): Vendor or foundation model checkpoint/release version, **strictly only when supported by verifiable repository evidence**; must be `null` for unknown, unverified, or internal procedural models. Never invent release numbers or conflate parameter sizes (e.g. `8b`) with software versions.
8. **`status` (str, Required):** Lifecycle availability status (see Section 6.5 for exact execution semantics).
9. **`provenance` (str, Required):** Default provenance classification of data produced by this model. Must match `ProvenanceType` enum (`observed`, `predicted`, `inferred`).
10. **`constraints` (Object, Required):**
    - `max_input_length` (int, > 0): Character or token input length limit.
    - `max_output_length` (int, > 0): Maximum expected output size.
    - `requires_network` (bool): Network/socket access requirement. Indicates whether the model requires socket communication (including local loopback HTTP such as `http://127.0.0.1:11434`, IPC sockets, or remote cloud APIs). **If `status == "production"`, `requires_network` must be `false`.**
    - `requires_gpu` (bool): GPU acceleration requirement.
    - `deterministic` (bool): Identical output for identical inputs.
11. **`configuration` (Object, Optional, default `{}`):** Static hyperparameter dictionary. **Resolved Configuration Invariant:** Procedural algorithms must NOT duplicate constants already defined in Python source code (e.g. `SKILL_TAXONOMY` in `resume_engine.py`). For deterministic models, `configuration` remains `{}`. For baseline clients, it holds non-sensitive client identifiers (e.g. `"model_name"`, `"api_key_env_var"`, `"host_env_var"`).
12. **`metadata` (Object, Optional, default `{}`):** Non-executable descriptive metadata. **Provenance Invariant:** `metadata.source_reference` is strictly human-readable audit text; it is NEVER used as an import path, dynamic module reference, or execution target.

### 6.4. Baseline Model Manifest Proposal (Evidence-Based from Codebase)

Every model proposed for the initial manifest is classified into exactly one repository evidence category:

- **`DETERMINISTIC_ALGORITHM`:** In-process Python algorithm exists in repository; PIE handler wrapper is not yet registered.
- **`IMPLEMENTED_INTEGRATION`:** Client/provider integration exists in repository code; host service availability is not assumed.
- **`REFERENCE_ONLY`:** Metadata or pricing references exist; executable support is not established. **Excluded from initial manifest.**
- **`CONFIGURED_IDENTIFIER`:** Identifier configured in environment/config, but executable integration is unverified. **Excluded from initial manifest.**

#### Codebase Evidence & Capability Justification Audit:

1. **`deterministic-ats-regex-v1` (`DETERMINISTIC_ALGORITHM`):**
   - *Source File:* `ml/nlp/resume_engine.py`
   - *Underlying Algorithms:* `ResumeEngine.score_against_job` (ATS scoring) and `ResumeEngine.parse_profile` (skill taxonomy regex extraction).
   - *Callable Structure:* Methods of the `resume_engine` singleton instance.
   - *Handler Wrappability:* Fully wrappable in a future statically registered PIE task handler without modifying legacy behavior.
   - *Justified Capabilities:* `["capability.resume.ats_score", "capability.text.keyword_match"]`.
   - *Document Parsing Exclusion:* In `ml/nlp/resume_engine.py`, `extract_text_from_pdf` is an unverified binary file extractor with optional C-extensions (`fitz`/`pypdf`). The core ATS scoring engine accepts pre-extracted `resume_text: str`. Conflating file-level document extraction with regex ATS scoring is unjustified. `capability.document.parse` is **strictly excluded** from this model.
2. **`deterministic-question-matrix-v1` (`DETERMINISTIC_ALGORITHM`):**
   - *Source File:* `backend/services/ai/local_question_engine.py`
   - *Underlying Algorithm:* `LocalQuestionEngine.generate_session_questions`.
   - *Callable Structure:* Standalone public method of the `local_question_engine` singleton instance.
   - *Handler Wrappability:* Fully wrappable in a future statically registered PIE task handler without modifying legacy behavior.
   - *Justified Capabilities:* `["capability.interview.question_structure"]`.
3. **`deterministic-metric-computer-v1` (`DETERMINISTIC_ALGORITHM`):**
   - *Source File:* `ml/nlp/resume_engine.py`
   - *Underlying Algorithm:* Impact metric regex extraction (`parse_profile` lines 121–136) and score breakdown calculation (`score_against_job` lines 202–205).
   - *Callable Structure:* **Internal subroutine logic** embedded within `ResumeEngine` methods. There is no standalone function named `calculate_metrics` in the codebase.
   - *Handler Wrappability:* A future PIE handler can invoke `parse_profile(text)["metrics_found"]` and compute metric breakdowns cleanly without modifying legacy code.
   - *Justified Capabilities:* `["capability.analytics.compute_metrics"]`. Documented explicitly as wrapping an internal subroutine.
4. **`baseline-ollama-llama3-8b` (`IMPLEMENTED_INTEGRATION`):**
   - *Source File:* `backend/app/providers/ollama_provider.py` (`OllamaProvider`), `backend/config.py`.
   - *Provider:* `ollama`.
   - *Upstream Version:* `null` (Repository config specifies `OLLAMA_MODEL = "llama3:8b"`; parameter size `8b` is not a software release version).
   - *Network Requirement:* `requires_network: true` (communicates over loopback HTTP socket `127.0.0.1:11434`; barred from production).
   - *Justified Capabilities:* `["capability.legacy.baseline_eval"]` (`status: "baseline_only"`).
5. **`baseline-gemini-2.0-flash` (`IMPLEMENTED_INTEGRATION`):**
   - *Source File:* `backend/services/ai/gemini_service.py` (`GeminiService`), `backend/config.py`.
   - *Provider:* `gemini`.
   - *Upstream Version:* `null` (Repository config specifies `GEMINI_MODEL = "gemini-2.0-flash"`; no vendor release version string exists in code).
   - *Network Requirement:* `requires_network: true` (communicates over external HTTPS API; barred from production).
   - *Justified Capabilities:* `["capability.legacy.baseline_eval"]` (`status: "baseline_only"`).
6. **`baseline-gemini-1.5-flash` & `baseline-gemini-1.5-pro` (`REFERENCE_ONLY`):**
   - *Source File:* Only present as pricing metadata in `backend/services/ai/pricing.py`. No dedicated active provider implementation exists. **Pruned and excluded from manifest.**

#### Evidence Summary Table:

| Proposed Model ID | Evidence Category | Repository Source Symbol | Provider ID | Callable Form | Upstream Version | Network / Socket Required | Justified Capabilities |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **`deterministic-ats-regex-v1`** | `DETERMINISTIC_ALGORITHM` | `ml/nlp/resume_engine.py` (`ResumeEngine`) | `internal_deterministic` | Class Method | `null` | **No** (In-process) | `capability.resume.ats_score`<br>`capability.text.keyword_match` |
| **`deterministic-question-matrix-v1`** | `DETERMINISTIC_ALGORITHM` | `backend/services/ai/local_question_engine.py` (`LocalQuestionEngine`) | `internal_deterministic` | Public Method | `null` | **No** (In-process) | `capability.interview.question_structure` |
| **`deterministic-metric-computer-v1`** | `DETERMINISTIC_ALGORITHM` | `ml/nlp/resume_engine.py` (`parse_profile` lines 121–136) | `internal_deterministic` | Internal Subroutine | `null` | **No** (In-process) | `capability.analytics.compute_metrics` |
| **`baseline-ollama-llama3-8b`** | `IMPLEMENTED_INTEGRATION` | `backend/app/providers/ollama_provider.py` (`OllamaProvider`) | `ollama` | Provider Class | `null` | **Yes** (Loopback HTTP) | `capability.legacy.baseline_eval` |
| **`baseline-gemini-2.0-flash`** | `IMPLEMENTED_INTEGRATION` | `backend/services/ai/gemini_service.py` (`GeminiService`) | `gemini` | Service Class | `null` | **Yes** (Remote HTTPS) | `capability.legacy.baseline_eval` |

#### Implementation-Ready Initial Manifest (`backend/pie/registry/models.json`):

```json
{
  "manifest_version": "1.0.0",
  "models": [
    {
      "model_id": "deterministic-ats-regex-v1",
      "name": "Procedural Regex ATS Skill Matcher & Scorer",
      "model_type": "heuristic",
      "provider": "internal_deterministic",
      "capabilities": [
        "capability.resume.ats_score",
        "capability.text.keyword_match"
      ],
      "input_modalities": ["text", "structured_data"],
      "output_modalities": ["structured_data", "json"],
      "version": "1.0.0",
      "upstream_version": null,
      "status": "production",
      "provenance": "observed",
      "constraints": {
        "max_input_length": 100000,
        "max_output_length": 50000,
        "requires_network": false,
        "requires_gpu": false,
        "deterministic": true
      },
      "configuration": {},
      "metadata": {
        "source_reference": "ml/nlp/resume_engine.py",
        "description": "High-performance procedural resume ATS scoring and keyword extraction engine based on compiled regex taxonomy."
      }
    },
    {
      "model_id": "deterministic-question-matrix-v1",
      "name": "Procedural Adaptive Question Structuring Engine",
      "model_type": "procedural_generator",
      "provider": "internal_deterministic",
      "capabilities": [
        "capability.interview.question_structure"
      ],
      "input_modalities": ["structured_data"],
      "output_modalities": ["structured_data", "json"],
      "version": "1.0.0",
      "upstream_version": null,
      "status": "production",
      "provenance": "inferred",
      "constraints": {
        "max_input_length": 50000,
        "max_output_length": 20000,
        "requires_network": false,
        "requires_gpu": false,
        "deterministic": true
      },
      "configuration": {},
      "metadata": {
        "source_reference": "backend/services/ai/local_question_engine.py",
        "description": "Procedural blueprint question generator calibrated to candidate resume taxonomy and claimed technologies."
      }
    },
    {
      "model_id": "deterministic-metric-computer-v1",
      "name": "Procedural Analytics & Metric Computation Engine",
      "model_type": "heuristic",
      "provider": "internal_deterministic",
      "capabilities": [
        "capability.analytics.compute_metrics"
      ],
      "input_modalities": ["structured_data"],
      "output_modalities": ["structured_data", "json"],
      "version": "1.0.0",
      "upstream_version": null,
      "status": "production",
      "provenance": "observed",
      "constraints": {
        "max_input_length": 50000,
        "max_output_length": 10000,
        "requires_network": false,
        "requires_gpu": false,
        "deterministic": true
      },
      "configuration": {},
      "metadata": {
        "source_reference": "ml/nlp/resume_engine.py",
        "description": "Deterministic metrics calculator producing quantified candidate evaluation metrics from resume subroutines."
      }
    },
    {
      "model_id": "baseline-ollama-llama3-8b",
      "name": "Ollama Llama 3 8B Local Baseline Runner",
      "model_type": "llm_external",
      "provider": "ollama",
      "capabilities": [
        "capability.legacy.baseline_eval"
      ],
      "input_modalities": ["text"],
      "output_modalities": ["text", "json"],
      "version": "1.0.0",
      "upstream_version": null,
      "status": "baseline_only",
      "provenance": "predicted",
      "constraints": {
        "max_input_length": 16000,
        "max_output_length": 4096,
        "requires_network": true,
        "requires_gpu": false,
        "deterministic": false
      },
      "configuration": {
        "model_name": "llama3:8b",
        "host_env_var": "OLLAMA_HOST"
      },
      "metadata": {
        "source_reference": "backend/app/providers/ollama_provider.py",
        "description": "Local loopback LLM runner used solely for comparative baseline evaluation. Prohibited from PIE production dispatch."
      }
    },
    {
      "model_id": "baseline-gemini-2.0-flash",
      "name": "Google Gemini 2.0 Flash External Baseline",
      "model_type": "llm_external",
      "provider": "gemini",
      "capabilities": [
        "capability.legacy.baseline_eval"
      ],
      "input_modalities": ["text"],
      "output_modalities": ["text", "json"],
      "version": "1.0.0",
      "upstream_version": null,
      "status": "baseline_only",
      "provenance": "predicted",
      "constraints": {
        "max_input_length": 32000,
        "max_output_length": 8192,
        "requires_network": true,
        "requires_gpu": false,
        "deterministic": false
      },
      "configuration": {
        "model_name": "gemini-2.0-flash",
        "api_key_env_var": "GEMINI_API_KEY"
      },
      "metadata": {
        "source_reference": "backend/services/ai/gemini_service.py",
        "description": "Legacy cloud LLM service retained for benchmark comparison. Prohibited from PIE production dispatch."
      }
    }
  ]
}
```

### 6.5. Model Status Semantics & Fail-Closed Selection Rules

#### Status Semantics:
- **`production`**: The model metadata is approved for production task selection **only when a matching statically registered handler is available in `ModuleRegistry` and policy permits execution**. The manifest entry represents declarative eligibility; it does NOT imply or guarantee that an executable handler exists.
- **`evaluation`**: Candidate model undergoing offline benchmarking or shadow testing. Excluded from production DAG selection.
- **`development`**: Experimental model undergoing local development. Excluded from production DAG selection.
- **`deprecated`**: Obsolete model marked for decommission. Excluded from production DAG selection.
- **`baseline_only`**: External or comparative reference model (e.g. legacy Gemini API or local Ollama). Retained exclusively for benchmark comparisons and regression testing against historical outputs. **Strictly barred from PIE production DAG routing.**

#### Fail-Closed Selection Rules (Zero Silent Fallback):

```
                        Coordinator Dispatch Request
                                    │
                                    ▼
                     Query ModelRegistry for Capability
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
       Model Found in Manifest?           Model NOT Found?
              /           \                         │
            No             Yes                      ▼
            │               │              FAIL CLOSED:
            │               │              Raise RegistryModelNotFoundError
            │               ▼
            │     Is status == "production"?
            │            /         \
            │          No           Yes
            │          │             │
            │          ▼             ▼
            │    FAIL CLOSED:   Query ModuleRegistry for Handler
            │    Raise Policy-       /         \
            │    ViolationError     No          Yes
            │    (Baseline/Dep)     │            │
            │                       ▼            ▼
            │                  FAIL CLOSED:   EXECUTE:
            │                  Raise Registry- Dispatch to
            │                  ModuleNotFound  Worker Thread
            ▼
     FAIL CLOSED:
     Raise RegistryModelNotFoundError
```

1. **Scenario 1: Model exists in `models.json` with `status: "production"`, but no handler is registered in `ModuleRegistry`:**
   - The coordinator query fails closed $\rightarrow$ raises `RegistryModuleNotFoundError(f"No executable handler registered for model '{model_id}'")`.
2. **Scenario 2: Capability exists in `Capability` enum, but no model with `status: "production"` supports it:**
   - The query `get_production_model_for_capability(cap)` fails closed $\rightarrow$ raises `RegistryModelNotFoundError(f"No production model approved for capability '{cap.value}'")`.
3. **Scenario 3: Only `baseline_only` models support the requested capability (e.g. `capability.legacy.baseline_eval`):**
   - The query `get_production_model_for_capability()` strictly ignores `baseline_only` models $\rightarrow$ raises `RegistryModelNotFoundError`.
   - The coordinator engine NEVER silently substitutes a `baseline_only` model into a production workflow.
4. **Scenario 4: Requested model is unknown, deprecated, development, or evaluation:**
   - Fails closed $\rightarrow$ raises `RegistryModelNotFoundError` (for unknown) or `PolicyViolationError` (for deprecated/dev/eval).
5. **No silent fallback under any circumstance.**

### 6.6. Recursive Security Validation (Credentials, Directives & Paths)

The manifest loader enforces a multi-layer recursive security inspection over `configuration`, `metadata`, `constraints`, and all nested objects/arrays before accepting the manifest. The loader traverses all nested mappings and sequences recursively, defending against object cycle graphs via an identity-visited set.

#### 1. Single Normalization Function:
All dictionary and mapping keys are normalized once using the following deterministic rule:
```python
norm_key = re.sub(r"[-_\s]", "", key).lower()
```

#### 2. Key Validation Pipeline & Sequential Precedence:
For every key-value pair `(key, val)` in any mapping within the manifest, validation executes in strict sequential order:

- **Pass 1: Dynamic Code & Import Directive Check:**
  - `DYNAMIC_CODE_KEYS = {"import", "module", "modulename", "callable", "function", "class", "classname", "handler", "exec", "eval", "code", "script", "lambda"}`
  - If `norm_key in DYNAMIC_CODE_KEYS`:
    Raise `SecurityPolicyViolationError(f"Dynamic code directive key '{key}' is prohibited in declarative manifest")`.

- **Pass 2: Environment Variable Pointer Precedence & Exception Check:**
  - If `norm_key.endswith("envvar")`:
    - The value `val` **must be a non-empty string**.
    - The value `val` **must strictly match the uppercase POSIX environment variable regex:**
      `^[A-Z][A-Z0-9_]{1,63}$`
      If `val` is empty, contains lowercase letters, starts with a number, or contains non-alphanumeric/underscore characters (e.g. `://`, `-`, `.`), the loader immediately raises:
      `SecurityPolicyViolationError(f"Environment variable pointer '{key}' must reference a valid uppercase POSIX identifier, got '{val}'")`.
    - In addition, `val` is scanned against high-confidence secret token patterns (Pass 4). If a literal credential pattern is detected, the loader immediately raises:
      `SecurityPolicyViolationError(f"Literal secret pattern detected in environment variable pointer '{key}'")`.
    - **Precedence Invariant:** If `val` satisfies all POSIX identifier rules and contains no secret pattern, the key is officially validated as an environment variable pointer and is **strictly exempted from Pass 3 (Prohibited Credential Substring Check)**.

- **Pass 3: Prohibited Credential Substring Check (Non-Exempt Keys Only):**
  - If the key was **not** exempted by Pass 2, `norm_key` is scanned against prohibited credential terms:
    `PROHIBITED_KEY_TOKENS = {"key", "apikey", "secret", "token", "password", "passwd", "auth", "credential", "credentials", "privatekey", "bearer"}`
  - If any prohibited token is a substring of `norm_key` (`any(tok in norm_key for tok in PROHIBITED_KEY_TOKENS)`):
    Raise `SecurityPolicyViolationError(f"Prohibited credential key '{key}' detected in manifest")`.

- **Pass 4: Value-Level Credential & High-Entropy Secret Detection:**
  - Every string value across all keys, arrays, and nested structures is scanned against high-confidence secret token patterns:
    - Google API keys: `r"^AIza[0-9A-Za-z-_]{35}$"`
    - OpenAI / Bearer secret tokens: `r"^sk-[a-zA-Z0-9]{32,}$"`
    - GitHub personal access tokens: `r"^ghp_[a-zA-Z0-9]{36}$"`
    - Private key headers: `r"-----BEGIN [A-Z ]*PRIVATE KEY-----"`
    - AWS access key IDs: `r"^AKIA[0-9A-Z]{16}$"`
    - HTTP Bearer auth headers: `r"^Bearer\s+[a-zA-Z0-9_\-\.~+/]+=*$"`
  - Any value matching these patterns raises `SecurityPolicyViolationError("Embedded credential pattern detected in manifest value")`.

#### 3. Handling of Descriptive Prose (No False Positives on "token" or Technical Terms):
Harmless English descriptive text containing words like `"token"`, `"tokens"`, `"tokenizer"`, `"passwordless"`, `"authenticated"`, or `"keyword"` (e.g. `"max_output_tokens"`, `"calculates token cost"`, `"tokenization strategy"`) in metadata or configuration string values is **explicitly permitted**. The key scanner targets dictionary key names for credential intent, while the value scanner uses anchored secret regexes, avoiding false-positive rejections of technical vocabulary.

#### 4. Proscription of Executable Directives & Path Traversal:
- **Path Separation Characters (`/` and `\`):** Standard path separators are **NOT universally rejected**. They are normal in human-readable documentation references (e.g. `"source_reference": "ml/nlp/resume_engine.py"`).
- **Prohibited Execution Protocols:** Any string value starting with dynamic execution protocol prefixes (`import:`, `eval:`, `exec:`, `python:`, `subprocess:`, `cmd:`) raises `SecurityPolicyViolationError`.
- **Prohibited Path Traversal:** Any string value containing path traversal sequences (`../`, `..\`) raises `SecurityPolicyViolationError`.
- **Prohibited Executable Extensions in Configuration:** Any string in `configuration` ending with executable script extensions (`.py`, `.sh`, `.bash`, `.bat`, `.cmd`, `.exe`, `.so`, `.dll`) raises `SecurityPolicyViolationError`.
- **Schema Proscription of Filesystem Loaders:** The manifest schema strictly prohibits any fields named `path`, `filepath`, `module_path`, `script_path`, or `load_from`. Handlers are registered exclusively via trusted static application code.

#### 5. Summary of Accepted vs. Rejected Key & Value Examples:

| Manifest Key & Value | Validation Result | Pass & Rationale |
| :--- | :---: | :--- |
| `"api_key_env_var": "GEMINI_API_KEY"` | **ACCEPTED** | Pass 2 matches `envvar` suffix; value is valid uppercase POSIX identifier; exempted from Pass 3. |
| `"host_env_var": "OLLAMA_HOST"` | **ACCEPTED** | Pass 2 matches `envvar` suffix; value is valid uppercase POSIX identifier; exempted from Pass 3. |
| `"source_reference": "ml/nlp/resume_engine.py"` | **ACCEPTED** | Non-executable documentation string; standard path separators permitted. |
| `"description": "Calculates candidate score and max_tokens"` | **ACCEPTED** | Technical vocabulary in prose value is permitted. |
| `"engine_type": "regex_and_keyword_counter"` | **ACCEPTED** | Plain declarative configuration string. |
| `"api_key": "AIzaSyD-1234567890abcdefghijklmnopqrst"` | **REJECTED** | Pass 3 catches prohibited key `api_key`; Pass 4 catches Google API key pattern. |
| `"secret_token": "live_token_value"` | **REJECTED** | Pass 3 catches prohibited credential keys `token` / `secret`. |
| `"api_key_env_var": "lowercase_api_key"` | **REJECTED** | Pass 2 fails: value contains lowercase letters; not a valid uppercase POSIX identifier. |
| `"api_key_env_var": "123_INVALID_VAR"` | **REJECTED** | Pass 2 fails: value starts with a digit; not a valid POSIX identifier. |
| `"api_key_env_var": "AIzaSyD-1234567890abcdefghijklmnopqrst"` | **REJECTED** | Pass 2 fails: value contains punctuation (`-`), lowercase, and matches Google API key regex. |
| `"host_env_var": "http://127.0.0.1:11434"` | **REJECTED** | Pass 2 fails: value is a literal URL containing punctuation (`://`), not an env var name. |
| `"handler": "ml.nlp.resume_engine.score"` | **REJECTED** | Pass 1 catches prohibited dynamic execution directive key `handler`. |
| `"script": "run_inference.sh"` | **REJECTED** | Pass 1 catches dynamic code key; Pass 4 catches executable script reference. |
| `"model_path": "../../weights/llama.bin"` | **REJECTED** | Pass 3 catches `model_path`; Pass 4 catches path traversal (`../`). |
| `"eval_code": "import:os; os.system('whoami')"` | **REJECTED** | Pass 1 catches code directive; Pass 4 catches execution protocol prefix (`import:`). |

#### 6. Declarative Invariant & Defense-in-Depth Disclaimer:
The loader is a static schema validator, NOT an operating-system sandbox. Manifest scanning provides automated defense-in-depth to catch accidental credential check-ins and injection vectors. Runtime security is strictly enforced by offline execution, process memory isolation, and the complete absence of `eval()`, `exec()`, or dynamic reflection on manifest values.

### 6.7. Model / Provider / Capability Relationship Matrix

The relationship between capabilities, production models, providers, and baseline references is strictly defined across the 5 verified entries:

| Capability Enum | Production Model (PIE R0) | Canonical Provider | Network / Socket Required | Execution Timeout Authority | Baseline Comparison Model (`baseline_only`) |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `capability.document.parse` | *(None - Unassigned in R0)* | N/A | N/A | TaskDefinition (max 15.0s) | N/A (Fails closed) |
| `capability.resume.ats_score` | `deterministic-ats-regex-v1` | `internal_deterministic` | **No** (In-process) | TaskDefinition (default 10.0s, max 15.0s) | N/A |
| `capability.text.keyword_match` | `deterministic-ats-regex-v1` | `internal_deterministic` | **No** (In-process) | TaskDefinition (default 10.0s, max 15.0s) | N/A |
| `capability.interview.question_structure` | `deterministic-question-matrix-v1` | `internal_deterministic` | **No** (In-process) | TaskDefinition (default 10.0s, max 15.0s) | `baseline-ollama-llama3-8b` |
| `capability.analytics.compute_metrics` | `deterministic-metric-computer-v1` | `internal_deterministic` | **No** (In-process) | TaskDefinition (default 10.0s, max 15.0s) | N/A |
| `capability.legacy.baseline_eval` | *(None - Baseline Only)* | N/A | N/A | Out-of-band benchmark harness | `baseline-gemini-2.0-flash`<br>`baseline-ollama-llama3-8b` |

### 6.8. Fail-Closed Validation Rules & Invariants

The `ModelRegistryLoader` executes the following sequential validation passes at load time. If any check fails, the loader immediately raises a specific domain error and refuses to populate the registry:

1. **Manifest File Accessibility & JSON Validity:**
   - Manifest file must exist at `backend/pie/registry/models.json`.
   - Content must be non-empty and parse cleanly with `json.loads(content)`. Syntax errors raise `RegistryManifestError`.
2. **Top-Level Envelope Schema:**
   - Must contain exact keys: `manifest_version`, `models`.
   - Unexpected top-level keys raise `UnexpectedFieldError`. Missing keys raise `MissingRequiredFieldError`.
   - `manifest_version` must be `"1.0.0"`. `models` must be a non-empty list.
3. **Exact Model Object Schema (No Unknown Fields):**
   - Each entry in `models` must contain all required fields: `model_id`, `name`, `model_type`, `provider`, `capabilities`, `input_modalities`, `output_modalities`, `version`, `upstream_version`, `status`, `provenance`, `constraints`.
   - `configuration` and `metadata` are optional objects (defaulting to `{}`).
   - Any unknown attribute (including obsolete `timeout_seconds`) raises `UnexpectedFieldError`.
4. **Duplicate Model ID Prohibition:**
   - Every `model_id` must be unique. Duplicate occurrences raise `DuplicateModelIdError`.
5. **Exact Enum Membership:**
   - `model_type` must be in `{"heuristic", "classifier", "procedural_generator", "statistical_ml", "llm_external"}`.
   - `provider` must be in `{"internal_deterministic", "ollama", "gemini"}`.
   - `status` must be in `{"production", "evaluation", "development", "deprecated", "baseline_only"}`.
   - `provenance` must be in `{"observed", "predicted", "inferred"}` (matching `ProvenanceType` enum).
   - Every item in `capabilities` must be an exact string value of `Capability` enum. Unknown capabilities raise `UnknownCapabilityError`.
6. **Constraint Numeric Bounds:**
   - `constraints.max_input_length` and `constraints.max_output_length` must be positive integers ($> 0$).
7. **R0 Network Isolation Policy:**
   - If `status == "production"`, `constraints.requires_network` **must be `false`**. Any model requiring socket communication (including local loopback HTTP like Ollama or remote cloud APIs like Gemini) is ineligible for production in R0.
   - If a production model declares `requires_network: true`, the loader immediately raises `ProductionNetworkPolicyError`.
8. **Recursive Security Scanner Execution:**
   - Recursively scans all `configuration`, `metadata`, and `constraints` structures per Section 6.6. Any violation raises `SecurityPolicyViolationError`.
9. **Fail-Closed Lookup Semantics (No Silent Fallback):**
   - Querying `registry.get_model("unknown_id")` raises `RegistryModelNotFoundError`.
   - Querying `registry.get_production_model_for_capability(cap)` raises `RegistryModelNotFoundError` if no model with `status: "production"` supports `cap`.
10. **Immutable Deep Freezing:**
    - After validation, each model definition is converted into a frozen `ModelMetadata` dataclass instance.
    - All nested mappings and lists are recursively converted to `MappingProxyType` and `tuple`.
    - The registry store itself is wrapped in an immutable `MappingProxyType[str, ModelMetadata]`.

### 6.9. Canonical Registry Exception Hierarchy & Ownership

To ensure strict architectural clarity, exception ownership is divided into two distinct groups: **frozen contract-level exceptions** (already implemented in Step 3B.1) and **registry-domain exceptions** (planned for implementation in Step 3B.2.3 under `backend/pie/registry/exceptions.py`).

#### Part A: Existing Contract Exceptions (Frozen in `backend/pie/contracts/exceptions.py`)
These classes are already implemented, tested, and sealed. They are imported directly into registry modules and must never be duplicated or modified:

1. `PIEException(Exception)`: Root base exception for all PIE domain errors.
2. `ContractViolationError(PIEException)`: Contract validation or immutability violation.
3. `PolicyViolationError(PIEException)`: Security or architectural policy rejection (e.g. attempting to dispatch a `baseline_only` or `deprecated` model in a production workflow).
4. `UnauthorizedCapabilityError(PIEException)`: Task requests a capability not authorized in `ExecutionContext`.
5. `WorkflowCycleError(PIEException)`: Circular dependency detected in workflow DAG.
6. `TaskTimeoutError(PIEException)`: Task execution exceeds deadline.
7. `RegistryModuleNotFoundError(PIEException)`: Missing executable handler in `ModuleRegistry` for an approved model.
8. `RegistryModelNotFoundError(PIEException)`: Requested model ID is missing from `ModelRegistry`, or no production model satisfies capability.

#### Part B: Proposed Registry-Domain Exceptions (Planned for `backend/pie/registry/exceptions.py`)
These classes are **planned for implementation in Step 3B.2.3**. They will inherit from `PIEException` (or its registry subclasses) and will be defined under `backend/pie/registry/exceptions.py`:

1. `RegistryError(PIEException)`: Base exception for all registry-domain failures.
2. `RegistryManifestError(RegistryError)`: `models.json` is missing, unreadable, or contains invalid JSON syntax.
3. `RegistrySchemaError(RegistryError)`: Structural schema validation failure in envelope or model definitions.
4. `MissingRequiredFieldError(RegistrySchemaError)`: Mandatory schema field missing from envelope or model entry.
5. `UnexpectedFieldError(RegistrySchemaError)`: Extraneous or unrecognized field (e.g. obsolete `timeout_seconds`) present.
6. `DuplicateModelIdError(RegistrySchemaError)`: Multiple model entries declare the same `model_id`.
7. `UnknownCapabilityError(RegistrySchemaError)`: Manifest declares a capability string not in `Capability` enum.
8. `CapabilityNotSupportedError(RegistryError)`: Query-time mismatch: requested model does not support the requested capability.
9. `SecurityPolicyViolationError(RegistryError)`: Prohibited credential key, secret pattern, dynamic code directive, or path traversal detected in manifest.
10. `ProductionNetworkPolicyError(RegistryError)`: Production model violates R0 policy (`requires_network: true`).
11. `RegistryInitializationError(RegistryError)`: Failure to load, freeze, or seal registry during startup.

#### Part C: Disambiguation of Failure Conditions & Exception Mapping:

| Failure Condition | Canonical Exception Class | Ownership (File) | Status in Workspace |
| :--- | :--- | :--- | :---: |
| **Unknown Model ID** | `RegistryModelNotFoundError(model_id)` | `backend/pie/contracts/exceptions.py` | **Implemented (Frozen)** |
| **No Production Model for Capability** | `RegistryModelNotFoundError(f"No production model approved for '{cap.value}'")` | `backend/pie/contracts/exceptions.py` | **Implemented (Frozen)** |
| **Model Capability Mismatch** | `CapabilityNotSupportedError(model_id, cap)` | `backend/pie/registry/exceptions.py` | *Planned (Step 3B.2.3)* |
| **Missing Registered Handler** | `RegistryModuleNotFoundError(model_id)` | `backend/pie/contracts/exceptions.py` | **Implemented (Frozen)** |
| **Policy Rejection (e.g. Baseline in Prod)** | `PolicyViolationError(f"Model '{model_id}' is baseline-only")` | `backend/pie/contracts/exceptions.py` | **Implemented (Frozen)** |

#### Concrete Planned Code for `backend/pie/registry/exceptions.py` (Step 3B.2.3):

```python
from typing import Optional
from backend.pie.contracts.exceptions import (
    PIEException,
    PolicyViolationError,
    RegistryModelNotFoundError,
    RegistryModuleNotFoundError,
    UnauthorizedCapabilityError,
)


class RegistryError(PIEException):
    """Base exception for all registry-domain errors."""
    def __init__(self, message: str, code: str = "REGISTRY_ERROR"):
        super().__init__(message, code)


class RegistryManifestError(RegistryError):
    """Raised when models.json is missing, unreadable, or invalid JSON."""
    def __init__(self, message: str):
        super().__init__(message, "REGISTRY_MANIFEST_ERROR")


class RegistrySchemaError(RegistryError):
    """Raised when manifest structure violates schema requirements."""
    def __init__(self, message: str, code: str = "REGISTRY_SCHEMA_ERROR"):
        super().__init__(message, code)


class MissingRequiredFieldError(RegistrySchemaError):
    """Raised when a mandatory manifest field is missing."""
    def __init__(self, field_name: str, model_id: Optional[str] = None):
        msg = f"Missing required field '{field_name}'" + (f" in model '{model_id}'" if model_id else "")
        super().__init__(msg, "MISSING_REQUIRED_FIELD")


class UnexpectedFieldError(RegistrySchemaError):
    """Raised when an unknown attribute is present in the manifest."""
    def __init__(self, field_name: str, model_id: Optional[str] = None):
        msg = f"Unexpected field '{field_name}'" + (f" in model '{model_id}'" if model_id else "")
        super().__init__(msg, "UNEXPECTED_FIELD")


class DuplicateModelIdError(RegistrySchemaError):
    """Raised when multiple models declare the same model_id."""
    def __init__(self, model_id: str):
        super().__init__(f"Duplicate model_id detected: '{model_id}'", "DUPLICATE_MODEL_ID")


class UnknownCapabilityError(RegistrySchemaError):
    """Raised when a model declares an unauthorized or unrecognized capability in the manifest."""
    def __init__(self, capability: str, model_id: str):
        super().__init__(f"Unknown capability '{capability}' in model '{model_id}'", "UNKNOWN_CAPABILITY")


class CapabilityNotSupportedError(RegistryError):
    """Raised at query time when a requested model does not support the requested capability."""
    def __init__(self, model_id: str, capability: str):
        super().__init__(f"Model '{model_id}' does not support capability '{capability}'", "CAPABILITY_NOT_SUPPORTED")


class SecurityPolicyViolationError(RegistryError):
    """Raised when manifest contains prohibited credentials, code directives, or executable paths."""
    def __init__(self, message: str):
        super().__init__(message, "SECURITY_POLICY_VIOLATION")


class ProductionNetworkPolicyError(RegistryError):
    """Raised when a production model violates R0 network isolation rules."""
    def __init__(self, model_id: str):
        super().__init__(
            f"Production model '{model_id}' violates R0 policy: requires_network must be False.",
            "PRODUCTION_NETWORK_POLICY_VIOLATION"
        )


class RegistryInitializationError(RegistryError):
    """Raised when registry fails to initialize or seal."""
    def __init__(self, message: str):
        super().__init__(message, "REGISTRY_INITIALIZATION_ERROR")
```

### 6.10. Immutable Snapshot Lifecycle (`ModelRegistry`)

The `ModelRegistry` class provides an in-memory, thread-safe, immutable snapshot store:

```python
class ModelRegistry:
    """Thread-safe, immutable in-memory registry of validated model metadata."""
    _instance: Optional["ModelRegistry"] = None
    _models: MappingProxyType  # Maps model_id -> ModelMetadata
    _capability_map: MappingProxyType  # Maps Capability -> Tuple[ModelMetadata, ...]
    _is_sealed: bool = False

    @classmethod
    def load_from_file(cls, manifest_path: Optional[str] = None) -> "ModelRegistry":
        """Loads, validates, freezes, and seals the registry from models.json."""
        ...

    def get_model(self, model_id: str) -> ModelMetadata:
        """Returns the immutable metadata for model_id; raises RegistryModelNotFoundError if missing."""
        ...

    def get_production_model_for_capability(self, capability: Capability) -> ModelMetadata:
        """
        Returns the primary production model for capability.
        Strictly excludes baseline_only, evaluation, and deprecated models.
        Raises RegistryModelNotFoundError if no production model satisfies capability.
        """
        ...

    def list_models(self, status: Optional[str] = None) -> Tuple[ModelMetadata, ...]:
        """Returns an immutable tuple of all registered models matching optional status."""
        ...
```

- **Thread-Safety:** Once loaded and sealed at application initialization, registry state is strictly read-only and backed by `MappingProxyType`. Multiple concurrent threads can query it without locks or race conditions.
- **Defensive Isolation:** Callers receive frozen `ModelMetadata` instances. Mutating any attribute or collection raises `TypeError` or `AttributeError`.

### 6.11. Comprehensive Testing Strategy for Model Registry

A dedicated test suite `backend/tests/test_pie_registry.py` will validate all registry behaviors across 7 core test classes:

1. **`TestManifestSchemaValidation`:**
   - Verifies required envelope fields (`manifest_version`, `models`).
   - Verifies rejection of unknown top-level and model-level keys (including obsolete `timeout_seconds`).
   - Verifies rejection of missing mandatory fields.
2. **`TestFailClosedManifestLoading`:**
   - Missing file raises `RegistryManifestError`.
   - Malformed JSON syntax raises `RegistryManifestError`.
   - Empty JSON document raises `RegistrySchemaError`.
3. **`TestModelIdentifierUniqueness`:**
   - Duplicate `model_id` entries raise `DuplicateModelIdError`.
   - Invalid `model_id` slug patterns raise `RegistrySchemaError`.
4. **`TestCapabilityAndEnumEnforcement`:**
   - Unknown capability strings raise `UnknownCapabilityError`.
   - Invalid `model_type`, `provider` (outside `internal_deterministic`, `ollama`, `gemini`), `status`, or `provenance` strings raise `RegistrySchemaError`.
   - Verifies that `capability.document.parse` lookup fails closed (`RegistryModelNotFoundError`).
5. **`TestConstraintAndPolicyValidation`:**
   - Negative constraint lengths raise `RegistrySchemaError`.
   - Production model declaring `requires_network: true` raises `ProductionNetworkPolicyError`.
   - Verifies that `baseline-ollama-llama3-8b` (`requires_network: true` for loopback socket) and `baseline-gemini-2.0-flash` (`requires_network: true` for remote API) are permitted only under `status: "baseline_only"`.
   - Verifies that execution timeout enforcement is delegated exclusively to `TaskDefinition` contract tests.
6. **`TestCredentialAndSecurityScanner`:**
   - Manifest containing credential keys (`"api_key"`, `"secret"`, `"password"`, `"bearer"`) raises `SecurityPolicyViolationError`.
   - Manifest containing dynamic import directives (`"import"`, `"module"`, `"callable"`) raises `SecurityPolicyViolationError`.
   - Manifest containing executable script paths or path traversal (`"../etc"`) raises `SecurityPolicyViolationError`.
   - Technical prose containing `"token"`, `"tokenizer"`, or path separators in documentation succeeds cleanly.
   - Permitted environment variable name references (`"api_key_env_var": "GEMINI_API_KEY"`) succeed cleanly.
   - Verifies zero external network requests during loading.
7. **`TestBaselineManifestIntegrity & Production Gating`:**
   - Loads canonical `backend/pie/registry/models.json` (5 verified baseline models).
   - Verifies all 5 baseline models are present, valid, and mapped to expected capabilities.
   - Verifies that `get_production_model_for_capability()` returns only `status == "production"` models and strictly rejects `baseline_only` models.
   - Verifies that snapshot inspection returns immutable `MappingProxyType` instances.

### 6.12. Implementation Sequence for Steps 3B.2.2 – 3B.2.5

The implementation of Step 3B.2 will proceed through four focused, sequential phases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.2.1: Model Registry Schema & Manifest Design (Current - Read-Only)  │
│ - Formalized JSON manifest schema, 5 baseline entries & security boundaries │
│ - Updated docs/architecture/pie_r0_step3a_core_design.md Section 6          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.2.2: Declarative Model Manifest Implementation                      │
│ - Author backend/pie/registry/models.json with 5 verified baseline models   │
│ - Verify zero credentials, correct capabilities, and strict offline format  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.2.3: Schema Dataclasses & Strict Fail-Closed Loader                 │
│ - Implement backend/pie/registry/schema.py (ModelMetadata, Constraints, etc)│
│ - Implement backend/pie/registry/exceptions.py (Registry domain hierarchy)  │
│ - Implement backend/pie/registry/loader.py (Strict fail-closed JSON loader) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.2.4: In-Memory ModelRegistry & Snapshot Interface                   │
│ - Implement backend/pie/registry/registry.py (Thread-safe query store)      │
│ - Implement backend/pie/registry/__init__.py (Sealed package exports)       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.2.5: Registry Test Suite & Compliance Audit                         │
│ - Author comprehensive backend/tests/test_pie_registry.py                   │
│ - Verify 100% test pass rate across all test suites (Contracts + Registry)  │
│ - Execute Step 3B.2 freeze audit before authorizing Step 3B.3               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.13. Architectural Risks, Trade-offs & Unresolved Dependencies

1. **Decoupling from Legacy Provider Fallback:**
   - In legacy code (`backend/services/ai/gemini_service.py`), Google Gemini falls back dynamically to local Ollama if an API error occurs.
   - In PIE R0, **silent provider fallback is strictly eliminated**. Workflow tasks declare exact capabilities and execute deterministic local procedural models. Baseline models (`baseline-gemini-*`, `baseline-ollama-*`) are classified as `baseline_only` and quarantined from production DAG routing.
2. **Standard Library JSON vs. PyYAML:**
   - Standard library `json` is chosen as the **sole canonical format** (`models.json`). This avoids introducing a runtime dependency on `PyYAML` and ensures deterministic parsing across all environments.
3. **Upstream Dependency Observation (`fitz` / PyMuPDF):**
   - The legacy resume parser (`ml/nlp/resume_engine.py`) imports `fitz` (PyMuPDF), emitting a deprecation warning (`warning: The fitz API is deprecated and will be removed in future. Use import pymupdf instead`).
   - In Step 3B.2, the registry merely records metadata for `deterministic-ats-regex-v1`; it does not alter or re-import `fitz`. When procedural handlers are linked in Step 3B.4, handler wrappers will encapsulate this cleanly.
4. **Static Capability Enumeration Integrity:**
   - Capabilities declared in `models.json` must always exist in `Capability` enum. If new capabilities are introduced in future milestones, `Capability` enum in `contracts/task.py` must be extended first before updating `models.json`. Loading fails closed if there is any mismatch.
5. **Document Parsing Capability Availability in R0:**
   - `Capability.DOCUMENT_PARSING` (`capability.document.parse`) is part of the frozen capability enum, but has no assigned production model in the initial manifest. In R0, querying for a production model supporting document parsing will fail closed (`RegistryModelNotFoundError`). Text extraction from PDF documents must occur prior to task dispatch, or a dedicated document parsing handler must be approved in a future update.

---

## 7. Policy Enforcement Boundaries & Safety Rules

Security boundaries in PIE are enforced before any task code is dispatched:

```
                    Task Dispatch Request
                             │
                             ▼
              ┌─────────────────────────────┐
              │    ExecutionPolicy Guard     │
              └──────────────┬──────────────┘
                             │
            Does capability exist in whitelist?
                           /   \
                     No   /     \   Yes
                         /       \
                        ▼         ▼
          ┌───────────────────┐  Does handler attempt raw SQL / Shell?
          │  REJECT:          │                     /   \
          │  PolicyViolation  │               Yes  /     \  No
          └───────────────────┘                   /       \
                                                 ▼         ▼
                                   ┌───────────────────┐  ┌───────────────────┐
                                   │  REJECT:          │  │  EXECUTE:         │
                                   │  SecurityFault    │  │  Task Dispatched  │
                                   └───────────────────┘  └───────────────────┘
```

### 7.1. Strict Policy Rules (`policy/rules.py`)
1. **Capability Authorization (Default-Deny):** A task can only execute if its requested capability is explicitly registered in the engine's `CapabilityPermissions` registry. Unregistered capabilities are denied immediately with `UnauthorizedCapabilityError`.
2. **Zero Shell Execution:** Handlers are strictly forbidden from importing `subprocess`, `os.system`, `popen`, or executing shell processes.
3. **Zero Arbitrary SQL:** Handlers cannot accept raw SQL strings from task inputs. Any future repository adapters must execute through parameterized query wrappers only.
4. **Zero Evaluation of Code Strings:** Modules must never use `eval()` or `exec()` on candidate inputs.
5. **No Network Egress in Core Tasks:** Core deterministic tasks must operate with `requires_network: false`. If a task requires network egress (e.g. future external baselines), it must be flagged explicitly as `baseline_only` and blocked from default execution.
6. **Handler Purity as an Architectural Invariant:** In R0, task handlers are strictly pure functions of their inputs: `handler(task_input: TaskInput) -> TaskOutput`. Handlers must not perform database writes, filesystem writes, network calls, global state mutations, or direct workflow state mutations. Only the coordinator engine may mutate workflow execution state (`task_results`, `StepStatus`, `WorkflowStatus`). This is an application-level architectural invariant enforced through code review, constrained handler registration in `ModuleRegistry`, and targeted isolation tests (not a bytecode-level CPython sandbox).

---

## 8. Error Handling, Timeouts, and Bounded Retries

### 8.1. ThreadPoolExecutor Timeout Semantics & Result Fencing
In CPython, calling `concurrent.futures.Future.cancel()` can only cancel queued tasks that have not yet started execution. It **cannot** interrupt, preempt, or kill a thread that is already running. Once a worker thread begins executing a handler, it runs to completion (or raises) regardless of whether the caller stops waiting.

To provide deterministic workflow behavior under this fundamental runtime constraint:
1. **Timeout Detection vs. Thread Abandonment:**
   - Execution is dispatched via `future = executor.submit(handler_wrapper, task_input, execution_token)`.
   - The engine waits via `future.result(timeout=effective_timeout)`.
   - If `TimeoutError` is raised, timeout detection occurs immediately. The engine marks the step as `StepStatus.TIMED_OUT` with `TaskTimeoutError`.
   - The underlying thread is **abandoned**—it continues executing in the background until the handler completes.
2. **Effective Timeout Calculation (Workflow vs. Task Deadline via Monotonic Clock):**
   - The task timeout cannot exceed the remaining workflow deadline:
     $$\text{remaining\_workflow\_time} = \max(0.0, \text{context.deadline\_mono} - \text{time.monotonic()})$$
     $$\text{effective\_timeout} = \min(\text{task.timeout\_seconds}, \text{remaining\_workflow\_time})$$
   - If $\text{remaining\_workflow\_time} \le 0.0$, the task is immediately recorded as `StepStatus.TIMED_OUT` without dispatching to the pool.
3. **Result Fencing via Execution Tokens & Side-Effect Boundaries:**
   - Every task dispatch generates a unique `execution_token = str(uuid.uuid4())` stamped on the step record.
   - If an abandoned thread finishes late and attempts to write its result, the dispatcher compares the result's token against the active token for that task ID.
   - If the task step was already marked `TIMED_OUT` (or a transient non-timeout retry generated a newer token), the late result is dropped, discarded, and logged as an orphaned late result.
   - **Side-Effect Boundary:** Result fencing strictly prevents stale results from modifying coordinator-owned workflow state (`task_results`, `StepStatus`, downstream inputs), but **cannot undo side effects** already performed by handlers. Therefore, for R0, handlers must be pure functions that return results without mutating shared workflow state, database tables, or globals. Only the coordinator engine may update task and workflow status. No side-effecting handlers are permitted in R0.
4. **Shutdown Behavior and Thread Drainage:**
   - When tearing down an engine, `executor.shutdown(wait=False, cancel_futures=True)` is called.
   - This immediately stops accepting new tasks (subsequent `submit` calls raise `RuntimeError`) and cancels unstarted tasks from the queue.
   - **Interpreter Exit Reality:** `wait=False` returns immediately to the caller without blocking in `shutdown()`, but running threads **cannot be forcibly terminated** and must finish naturally. Standard library worker threads are non-daemon, meaning CPython interpreter exit will still wait for running threads to terminate. Guaranteed immediate interpreter termination is not claimed; all PIE handlers must adhere to bounded, short-lived execution expectations ($O(N)$ CPU operations).

### 8.2. Bounded Retries, Idempotency & Concurrency Overlap Protection
- **Bounded Retries:** Default `max_retries = 0` (no retry). The engine enforces a hard upper bound of `max_retries <= 2`.
- **Explicit Idempotency Requirement:** A task is **never** retried unless its definition explicitly sets `is_idempotent = True`. Non-idempotent operations fail permanently on the first error.
- **Timeout Retries Strictly Prohibited in R0:**
  - For all R0 execution, **timeout retries are strictly prohibited engine-wide** (`retry_on_timeout = False` enforced unconditionally).
  - Explicit idempotency metadata (`is_idempotent: bool`) is retained in `TaskDefinition` solely for forward-compatibility with future milestones, but is **not** used to enable timeout retries in R0.
  - A timed-out task unconditionally transitions directly to `StepStatus.TIMED_OUT`. No timeout retry is permitted under any circumstances, even if `is_idempotent = True`.
  - This guarantees that an uncancelable worker thread continuing in the background after timeout will never race against a duplicate concurrent retry attempt of the same task.
- **Ordinary Non-Timeout Retries:**
  - Only transient resource contention errors (such as thread pool submission failure or temporary lock wait) on tasks explicitly declared with `is_idempotent = True` are eligible for bounded retry up to `max_retries <= 2`.
- **Non-Retryable Error Categories:**
  - `ContractViolationError` (invalid payload, missing fields — will never succeed on retry).
  - `PolicyViolationError` & `UnauthorizedCapabilityError` (security policy rejection is deterministic).
  - `InternalFault` (unhandled Python runtime bug in handler code).
  - `TaskTimeoutError` in R0 (all timeouts are non-retryable in R0).
  - Any error where `is_idempotent = False`.
- **Exponential Backoff Arithmetic:**
  $$\text{delay} = \text{backoff\_factor} \times 2^{\text{attempt}}$$
  (Attempt 1: 0.5s backoff; Attempt 2: 1.0s backoff; Attempt 3: Exceeded -> step marked `StepStatus.FAILED`).

### 8.3. Error Taxonomy (`evaluation/taxonomy.py`)

| Error Category | Examples | Retryable? | Metric Recorded |
| :--- | :--- | :--- | :--- |
| **`CONTRACT_ERROR`** | Missing required payload key, type mismatch, invalid UUID. | **NO** | `error.contract_violation` |
| **`POLICY_ERROR`** | Unauthorized capability, blocked provider, shell attempt. | **NO** (Security Event) | `security.policy_violation` |
| **`TIMEOUT_ERROR`** | Task execution exceeded `effective_timeout`. | **NO (Strictly prohibited in R0)** | `error.task_timeout` |
| **`TRANSIENT_RESOURCE_ERROR`** | Thread pool saturation, temporary lock contention. | **YES (Bounded: max <= 2, only if is_idempotent=True)** | `error.transient_resource` |
| **`INTERNAL_FAULT`** | Unhandled Python runtime exception (`AttributeError`, `TypeError`). | **NO** | `error.internal_fault` |

---

## 9. Comprehensive Testing Strategy for PIE Core

A four-tier test suite will be implemented in `backend/tests/` to guarantee absolute isolation and correctness:

### 9.1. Unit Test Matrix
1. **Contract Validation Suite (`test_pie_contracts.py`):**
   - Validates `APPROVED_CONTRACT_TYPES`: enforces exact concrete-type membership (`type(obj) in APPROVED_CONTRACT_TYPES`) for `ExecutionContext`, `TaskInput`, `TaskOutput`, `TaskResult`, `TaskDefinition`, `WorkflowDefinition`, and `ExecutionResult`.
   - Asserts rejection of unapproved `BaseContract` subclasses: defines an unregistered subclass of `BaseContract` and asserts it is rejected with `ContractViolationError`, confirming inheritance alone is insufficient.
   - Asserts rejection of duck-typed objects: arbitrary custom objects implementing `.to_dict()` without registration raise `ContractViolationError`.
   - Asserts recursive `.to_dict()` validation: during unfreezing, `.to_dict()` outputs of nested contracts are recursively re-validated through `unfreeze_to_dict()`, ensuring unapproved mutable types or invalid values returned by custom `.to_dict()` implementations cannot bypass the serialization boundary.
   - Asserts recursive immutability: mutating nested dictionaries, lists, or sets raises `TypeError` or `AttributeError`.
   - Asserts aliasing protection: mutating caller-owned input structures (`dict`, `list`, `set`) after passing to contracts does not alter frozen contract state.
   - Asserts cycle detection via active call stack: genuine cyclic references ($A \to B \to A$ or self-references) are rejected with `ContractViolationError`.
   - Asserts shared-reference DAG traversal: diamond reference structures ($A \to [B, C]$ where both $B$ and $C$ reference container $D$) are traversed and frozen successfully without false-positive cycle errors.
   - Asserts strict subclass type-check ordering: verifies `bool` is not evaluated as `int` (`True` remains `True`), and `IntEnum` is evaluated as an `Enum` (serialized to `.value`) rather than a primitive integer.
   - Asserts payload set prohibition: passing `set` or `frozenset` inside a JSON-bound task payload (`TaskInput.payload`, `TaskOutput.data`) raises `ContractViolationError`.
   - Asserts string-only internal sets: internal contract sets/frozensets accept only `str` elements (`frozenset[str]`); sets containing non-string elements (e.g. `int`, `float`, or mixed heterogeneous items) raise `ContractViolationError`. Deterministic serialization uses standard lexicographical sorting (`sorted(obj)`).
   - Asserts unsupported types (custom class instances, generators, non-finite floats, non-string mapping keys) are rejected with `ContractViolationError`.
   - Validates monotonic deadline calculation (`deadline_mono`, `time.monotonic()`).
   - Tests `ProvenanceType`, `StepStatus`, `WorkflowStatus`, and `Capability` enum parsing.
2. **DAG & Cycle Detection Suite (`test_pie_dag.py`):**
   - Validates linear graph topologies (A -> B -> C).
   - Validates diamond graph topologies (A -> [B, C] -> D).
   - Injects circular dependencies (A -> B -> C -> A) and confirms `WorkflowCycleError` is raised with the exact cycle path.
   - Asserts missing dependency raises `ContractViolationError`.
   - Validates topological stage sorting order.
3. **Model & Module Registry Suite (`test_pie_registry.py`):**
   - Tests loading of canonical `models.json` (and optional `models.yaml`).
   - Confirms `status: "baseline_only"` models are flagged and rejected from production dispatch.
   - Tests duplicate module registration raises `DuplicateModuleError`.
   - Confirms querying missing capability raises `RegistryModuleNotFoundError`.
4. **Policy Guard Suite (`test_pie_policy.py`):**
   - Tests default-deny rejection of unregistered capabilities.
   - Tests that task handlers cannot invoke unauthorized operations.
5. **Execution Engine & Runner Suite (`test_pie_engine.py`):**
   - Tests synchronous in-process task execution with deterministic mock handlers across topological stages.
   - Tests timeout enforcement: task exceeding `effective_timeout` (computed via monotonic clock) raises `TaskTimeoutError` and transitions to `StepStatus.TIMED_OUT`.
   - Tests timeout retry invariant: timed-out task is **strictly never retried** in R0, even if `is_idempotent=True`.
   - Tests bounded retry arithmetic: transient resource contention errors on idempotent tasks retry up to `max_retries` ($\le 2$).
   - Tests result fencing: late result with stale execution token from abandoned worker thread is discarded and cannot alter coordinator state.
   - Tests handler purity: handlers execute without mutating shared engine state or global variables.
   - Tests shutdown behavior: `shutdown(wait=False, cancel_futures=True)` cancels queued tasks, rejects new tasks, and allows running worker threads to finish naturally.
   - Tests deterministic evaluator rubric (bounds check, confidence range).

### 9.2. Isolation & Non-Disruptive Coexistence Tests
- **Import-Time Side-Effect Test (Subprocess-Isolated):**
  - Confirms that `import pie` in a fresh Python process makes zero database connections and loads zero external LLM SDKs.
- **Feature-Flag Guard Test:**
  - With `PIE_ENABLED=false`: Flask application boots without initializing PIE; existing legacy endpoints operate with 100% parity.
- **Legacy Regression Continuity:**
  - All existing 72 backend tests (`test_step2a_config.py`, `test_step2b1_ip_rate_limiter.py`, `test_step2b2_credential_sanitization.py`, `test_step2c_recording_architecture.py`) must pass with zero modifications.

---

## 10. Dependencies & Compatibility Analysis

### 10.1. Current Environment Audit
- **Host Runtime:** Python 3.14.4
- **Container Target:** Python 3.11-slim
- **Installed Packages (`requirements.txt`):** `flask`, `flask-cors`, `python-dotenv`, `gunicorn`, `pyjwt`, `werkzeug`, `google-genai`, `pymupdf`, `ollama`, `flask-sock`, `requests`, `psycopg2-binary`, `certifi`.
- **Observed Gap:** Neither `pydantic` nor `pyyaml` is present in `requirements.txt`.

### 10.2. Dependency Strategy for Step 3B
To maintain maximum stability and eliminate installation hurdles:

| Component | Recommended Technology | Rationale & Trade-Off Analysis |
| :--- | :--- | :--- |
| **Contracts & Schemas** | **Python Standard Library `dataclasses` (`@dataclass(frozen=True)`) + `APPROVED_CONTRACT_TYPES` + `types.MappingProxyType` + `tuple` + `frozenset[str]`** | **Zero dependencies.** Supported natively across Python 3.11 and 3.14. Deeply immutable via recursive defensive copying, exact concrete-type membership enforcement (`type(obj) in APPROVED_CONTRACT_TYPES`), circular-import-safe registration (`@register_contract`), active call-stack cycle detection (supporting diamond DAG references), payload set prohibition, string-only internal sets (`frozenset[str]`) with lexicographical sorting, strict subclass type ordering (bool/Enum before int), deterministic serialization via explicit `.to_dict()` / `unfreeze_to_dict()`, and recursive validation of nested contracts. (Avoids relying on `dataclasses.asdict()`). |
| **Model Registry File Format** | **Standard Library `json` (`models.json`)** | **Canonical Zero-Dependency Format.** Bundled at `backend/pie/registry/models.json`. Parsed using standard library `json.load()`. Zero new dependencies required in `requirements.txt`. (Optional fallback parser for `models.yaml` is provided if `pyyaml` is present in the environment, but `models.json` is the canonical authoritative source). |
| **Workflow Thread Pool** | **Python Standard Library `concurrent.futures.ThreadPoolExecutor`** | **Zero dependencies.** Built-in bounded concurrency, future timeout handling, and exception propagation without Celery or Redis. |

---

## 11. Exact Implementation Sequence for Step 3B Onward

Implementation of PIE Core will be decomposed into small, independently reviewable substeps:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.1: Core Contracts, Deep Immutability & Domain Exceptions            │
│ - Create backend/pie/__init__.py, contracts/context.py, task.py, results.py │
│ - Implement deep immutability via MappingProxyType & tuple casting          │
│ - Implement PIEException hierarchy (prefixed names to prevent shadowing)    │
│ - Focused unit tests in test_pie_contracts.py                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.2: Model & Module Registries                                        │
│ - Create backend/pie/registry/models.json (canonical offline registry)      │
│ - Implement ModelRegistry and ModuleRegistry                                │
│ - Validate lifecycle status (baseline_only models blocked from production)  │
│ - Focused unit tests in test_pie_registry.py                                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.3: Workflow DAG Engine & Cycle Detection                            │
│ - Create backend/pie/workflow/dag.py, validator.py, ordering.py             │
│ - Implement 3-color DFS cycle detector & topological stage partitioner      │
│ - Focused unit tests in test_pie_dag.py                                     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.4: Execution Engine, Dispatcher, Result Fencing & Policy Guard      │
│ - Create backend/pie/engine/runner.py, executor.py, dispatcher.py           │
│ - Create backend/pie/policy/guard.py, rules.py                              │
│ - Implement result fencing with execution_tokens, timeout abandonment,      │
│   idempotency checks, bounded retries, and capability authorization         │
│ - Focused unit tests in test_pie_engine.py & test_pie_policy.py             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.5: Evaluators, Passive Health Diagnostics & Flask Factory Hook      │
│ - Create backend/pie/evaluation/recorder.py, evaluators.py, taxonomy.py     │
│ - Create backend/pie/health/checker.py, status.py (passive-only checks)     │
│ - Wire optional PIE health check into main.py (guarded by PIE_ENABLED=true) │
│ - Full regression suite (72 existing tests + new PIE tests)                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Risks, Trade-offs, and Final Architecture Decisions

1. **Dataclasses with Deep Immutability vs. Pydantic v2:**
   - *Decision:* Python standard library frozen dataclasses enhanced with `MappingProxyType` and `tuple` casting provide a robust, deeply immutable, zero-dependency foundation for R0. Pydantic v2 is deferred to avoid C-extension compilation risks and packaging friction across Python 3.11 and 3.14.
2. **In-Process Thread Pool vs. Distributed Celery/Redis:**
   - *Decision:* PIE R0 workloads are short-lived, synchronous analytical tasks (parsing, ATS scoring, rubric validation). Celery or Redis would introduce infrastructure debt, distributed state synchronization bugs, and deployment friction. `ThreadPoolExecutor(max_workers=4)` per Gunicorn process is strictly contained, production-safe, and requires zero external services.
3. **Canonical Model Registry File Format:**
   - *Decision:* `models.json` is officially adopted as canonical for Step 3B. Storing metadata in JSON eliminates any need to modify `backend/requirements.txt` or install `pyyaml`.

---

## 13. Architecture Risk Corrections and Final Decisions

This section addresses specific engineering feedback and formalizes architectural corrections prior to any Step 3B implementation.

### 13.1. ThreadPoolExecutor Timeout Semantics & Execution Fencing

#### The CPython Thread Limitation
In CPython, calling `Future.cancel()` on a `concurrent.futures.Future` can **only** cancel pending tasks waiting in the executor queue. Once a worker thread has popped a task and begun execution, calling `.cancel()` returns `False` and has **zero effect** on the running thread. The Python runtime provides no safe, portable mechanism to preempt, interrupt, or forcibly kill a running thread.

#### Timeout Detection vs. Actual Task Termination
When a task's deadline expires during `future.result(timeout=effective_timeout)`, a `concurrent.futures.TimeoutError` is raised in the engine's coordinator thread. The engine immediately detects the timeout and records `StepStatus.TIMED_OUT`. However:
- The underlying worker thread is **not terminated**.
- The worker thread is **abandoned** from the perspective of the workflow coordinator.
- The thread continues executing the handler until it naturally returns, raises an exception, or the host process terminates.

#### Result Fencing via Execution Tokens
Because an abandoned worker thread may continue executing for several seconds after a timeout has been recorded, a mechanism is required to prevent "zombie" results from corrupting the workflow or downstream tasks.

PIE solves this via **Result Fencing**:
1. At dispatch time, the engine generates a cryptographically random `execution_token = str(uuid.uuid4())`.
2. The `execution_token` is stamped onto the internal step state record and passed into the task wrapper.
3. When any worker thread completes, the task wrapper submits the result back to the coordinator accompanied by its assigned `execution_token`.
4. The coordinator validates the token:
   - If the task step is still in `RUNNING` status and the token matches the active `execution_token`, the result is accepted.
   - If the task step was already marked `TIMED_OUT`, `FAILED`, or `SKIPPED`, or if a newer token was issued (e.g. during a transient non-timeout retry), the incoming result is **rejected and dropped**.
   - A warning log is emitted (`orphaned_result_dropped`), and the workflow's state remains strictly protected from late mutations.

#### Workflow Deadline vs. Task Deadline Interaction (Monotonic Clock)
To prevent an individual task from executing past the overall workflow's time budget:
1. The `ExecutionContext` computes and carries a monotonic deadline: `deadline_mono = time.monotonic() + timeout_seconds`. Using `time.monotonic()` ensures deadline calculations are strictly elapsed-time measurements, immune to system clock shifts, NTP adjustments, or wall-clock skew.
2. Before dispatching any task, the engine computes:
   $$\text{remaining\_workflow\_time} = \max(0.0, \text{context.deadline\_mono} - \text{time.monotonic()})$$
   $$\text{effective\_timeout} = \min(\text{task.timeout\_seconds}, \text{remaining\_workflow\_time})$$
3. If $\text{remaining\_workflow\_time} \le 0.0$, the task is not dispatched at all; it is marked `StepStatus.TIMED_OUT` immediately with an informative message (`"Workflow deadline expired before dispatch"`).
4. When waiting on the future, the engine waits for at most `effective_timeout` seconds.

#### ThreadPoolExecutor Shutdown Semantics and Interpreter Exit Reality
When tearing down an engine or worker pool:
- The engine's shutdown procedure calls `executor.shutdown(wait=False, cancel_futures=True)`.
- This immediately stops accepting new tasks (subsequent `submit()` calls raise `RuntimeError`) and cancels all unstarted queued futures from the executor queue.
- **CPython Process Exit Reality:** Calling `wait=False` merely returns immediately to the caller without blocking in `shutdown()`. However, worker threads created by standard library `ThreadPoolExecutor` are non-daemon. At process exit, CPython's threading runtime executes an atexit handler that joins all active non-daemon threads! Therefore, running worker threads **cannot be forcibly terminated**, and if a thread is hung in an infinite loop or blocked on an uninterruptible syscall, the interpreter will wait for it upon exit.
- Consequently, PIE does **not** claim guaranteed instantaneous interpreter termination. Instead, all PIE handlers must be bounded in execution (CPU-bound $O(N)$ deterministic algorithms with predictable latency).

---

### 13.2. Retry Safety, Idempotency, and Concurrency Controls

#### Explicit Retry Policy
Uncontrolled retries in an in-process threaded engine create serious hazards, including thread pool exhaustion and race conditions. PIE R0 implements a strict, bounded retry policy:
- **Default Retries:** `max_retries = 0` (no retries by default).
- **Upper Bound:** `max_retries` cannot exceed `2`.
- **Pre-condition:** Only tasks with `is_idempotent = True` can ever be retried.

#### Timeout Retries Strictly Prohibited in R0
- For all R0 execution, **timeout retries are strictly prohibited engine-wide** (`retry_on_timeout = False` enforced unconditionally).
- A task experiencing timeout transitions directly and permanently to `StepStatus.TIMED_OUT`. No timeout retry is permitted under any circumstances, even if `is_idempotent = True`.
- Explicit idempotency metadata (`is_idempotent: bool`) is retained in `TaskDefinition` solely for schema forward-compatibility with future milestones, but is **never** used to permit timeout retries in R0.
- *Rationale:* When an uncancelable worker thread times out and continues running in the background, launching a retry creates concurrent duplicate execution of the same logical task, doubling resource consumption and risking race conditions. By disabling timeout retries in R0, thread overlap risk is eliminated completely.
- **Ordinary Non-Timeout Retries:** Only transient resource contention errors (such as thread pool submission failure or temporary lock wait) on tasks explicitly declared with `is_idempotent = True` are eligible for bounded retry up to `max_retries <= 2`.

#### Strict Non-Retryable Error Categories
The engine classifies errors immediately upon failure. The following categories are **strictly non-retryable**:
1. **Contract Violations (`ContractViolationError`):** Missing fields, type errors, or malformed inputs cannot be cured by repeating the exact same function call.
2. **Policy Violations (`PolicyViolationError`, `UnauthorizedCapabilityError`):** Access control decisions are deterministic; retrying an unauthorized capability will always fail.
3. **Internal Logic Faults (`InternalFault`, unhandled Python exceptions):** Bugs in handler implementation (`AttributeError`, `IndexError`, `TypeError`) are deterministic faults. Retrying them wastes CPU cycles and clogs the worker pool.
4. **Task Timeouts in R0 (`TaskTimeoutError`):** Strictly non-retryable in R0.
5. **Non-Idempotent Tasks (`is_idempotent = False`):** Any task that is not explicitly declared idempotent fails permanently on the first error to protect data integrity.

---

### 13.3. Policy Enforcement Boundaries & Logical Pre-Dispatch Gating

#### Logical Gatekeeper vs. Process Sandbox
It is critical to clearly define the boundary of PIE R0 policy enforcement:
- **What PIE Policy IS:** A **logical authorization and contract gatekeeper** evaluated *before* a task is submitted to the execution queue. It ensures that the requested workflow, task, and caller conform to registered capabilities, whitelisted module IDs, and structured data schemas.
- **What PIE Policy IS NOT:** It is **NOT** an operating-system sandbox, a hardware isolation boundary (e.g. seccomp, gVisor, or Docker container isolation), or an interpreter sandbox. In standard CPython, any Python code executing in the same process has access to `sys.modules`, `ctypes`, and built-in namespace primitives.

#### Threat Model and Defense-in-Depth
- **Trusted Codebase Assumption:** In R0, all task handlers are part of the reviewed, trusted application codebase. PIE defends against **developer error, improper workflow composition, unintended capability escalation, and unvetted data flow**, not against active hostile bytecode execution inside the Python process.
- **Input Payload Insulation:** Untrusted user input (such as resume text or candidate interview responses) is passed strictly as data inside `TaskInput.payload` (wrapped in a read-only `MappingProxyType`). User input **never** touches module resolution, handler importation, or capability assignment.
- **Static Capability Binding:** A task's `capability` is statically declared in its `TaskDefinition`. The policy guard inspects this declaration against the `CapabilityPermissions` registry. If a handler attempts an unauthorized action or an unregistered capability is requested, the policy guard aborts execution before dispatch.
- **Prohibition of Shell and Raw SQL:** Handlers must adhere to architectural invariants: zero execution of `subprocess` / `os.system` and zero execution of dynamic unparameterized SQL strings. These invariants are verified via static linting and targeted unit tests.

#### Result Fencing and Side-Effect Boundaries
- Result fencing prevents stale results from modifying coordinator-owned workflow state (`task_results`, `StepStatus`, downstream task inputs).
- **Critical Limitation:** Result fencing **cannot undo side effects** already performed by handlers (e.g. database writes, external network calls, or filesystem mutations).
- For R0, the following invariants are enforced:
  1. Handlers must be pure functions: they accept immutable `TaskInput` and return immutable `TaskOutput`.
  2. Handlers must **never directly mutate shared workflow state**, database records, or global variables.
  3. Only the coordinator engine may update task and workflow status.
  4. No side-effecting handlers exist in the initial R0 engine.
  5. Stale execution tokens can never publish late results or trigger downstream stage execution.

---

### 13.4. Recursive Contract Immutability, Defensive Copying & Serialization

#### The Shallow Immutability and Aliasing Vulnerability
Python's standard library `@dataclass(frozen=True)` enforces immutability only at the top level: attempting `context.trace_id = "new"` raises `FrozenInstanceError`. However, two critical vulnerabilities remain if not recursively handled:
1. **Nested Mutable Structures:**
   ```python
   # With shallow dataclass freezing:
   context.metadata["tampered"] = True        # SUCCEEDS if metadata is a plain dict!
   task_input.payload["injected"] = "malice"  # SUCCEEDS if payload is a plain dict!
   ```
2. **Aliasing Mutation (Retained References):**
   If a caller constructs `raw_payload = {"skills": ["python", "sql"], "nested": {"val": 1}}` and passes it to `TaskInput(..., payload=raw_payload, ...)`, even if the top-level dictionary is wrapped in `MappingProxyType(dict(raw_payload))`:
   ```python
   raw_payload["nested"]["val"] = 999         # MUTATES input inside TaskInput!
   raw_payload["skills"].append("c++")        # MUTATES list inside TaskInput!
   ```
   Retained caller references to nested objects break immutability across concurrent worker threads.

#### Deep Recursive Immutability via Standard Library
PIE R0 achieves deep recursive immutability and aliasing protection without adding external dependencies:
1. **Explicit Supported-Value Contract & Defensive Copying (`freeze_immutable`):**
   - The constructor recursively traverses and defensively copies all incoming structures before freezing:
     - `dict` $\rightarrow$ `MappingProxyType` of recursively frozen key-values. **Keys must be strings (`str`)**. Non-string keys raise `ContractViolationError`.
     - `list` / `tuple` / sequence $\rightarrow$ immutable `tuple` of recursively frozen items.
     - `set` / `frozenset` $\rightarrow$ immutable `frozenset[str]`. In R0, internal sets are strictly string-only (e.g. `TaskDefinition.depends_on`). Sets containing non-string elements or mixed types raise `ContractViolationError`. **Payload Restriction:** Sets and frozensets are strictly prohibited in JSON-bound task payloads (`TaskInput.payload`, `TaskOutput.data`, `ExecutionResult.task_results`); callers must use ordered lists or tuples.
     - Primitives: strictly `str`, `int`, finite `float` (`math.isfinite(x)`: non-finite floats like `inf`/`nan` raise `ContractViolationError`), `bool`, and `None`.
     - Identifiers & Enums: `uuid.UUID` and `Enum` instances.
     - **Approved Contracts (`APPROVED_CONTRACT_TYPES`):** Enforces exact concrete-type membership: `type(obj) in APPROVED_CONTRACT_TYPES`. The approved allowlist contains only concrete R0 classes (`ExecutionContext`, `TaskInput`, `TaskOutput`, `TaskResult`, `TaskDefinition`, `WorkflowDefinition`, `ExecutionResult`). Unregistered subclasses of `BaseContract` and duck-typed objects with `.to_dict()` are strictly rejected with `ContractViolationError`. Circular imports are prevented by defining `@register_contract` in `contracts/base.py`, allowing contract modules to register themselves without `base.py` importing downstream modules.
     - **Strict Subclass Type-Check Ordering:** Because `issubclass(bool, int)` and `issubclass(IntEnum, int)` are True, type checks strictly evaluate `bool` and `Enum` before `int`, preventing `bool` and `IntEnum` from being misidentified as primitive integers.
     - **Unsupported Objects Rejected:** Arbitrary custom objects, mutable class instances, generators, lambdas, unregistered `BaseContract` subclasses, and non-contract dataclasses are strictly rejected with `ContractViolationError`. Arbitrary Python objects are never assumed to be immutable.
     - **Active Call-Stack Cycle Detection:** Recursive traversal tracks the active recursion stack via `active_path = set()` using container `id(obj)` with `try...finally`. Genuine cycles ($A \to B \to A$) raise `ContractViolationError`, while shared-reference DAG structures (diamond references $A \to [B, C]$ where $B, C \to D$) are cleanly permitted without false positives.
   - **Cost Model:** While wrapping a dictionary in `MappingProxyType` is an $O(1)$ pointer wrapper, recursive traversal and defensive copying is $O(M)$ over the payload element count $M$. This defensive copying cost is an intentional, acceptable architectural trade-off to completely eliminate object aliasing and retained caller reference mutation.
2. **Explicit Serialization Contract (`unfreeze_to_dict` / `.to_dict()`):**
   - Standard library `dataclasses.asdict()` cannot be assumed to handle `MappingProxyType` or recursively frozen structures reliably across Python versions (in Python 3.11 and 3.14, `asdict()` uses a dictionary factory that may preserve `MappingProxyType` or fail depending on internal copy logic).
   - Therefore, PIE establishes an explicit serialization contract: every contract class implements a `.to_dict()` method powered by `unfreeze_to_dict(obj)`, which recursively unfreezes proxies, tuples, and frozensets back into standard Python `dict` and `list` structures.
   - When an approved contract is unfrozen, its `.to_dict()` output is itself recursively passed back through `unfreeze_to_dict()`, ensuring internal fields cannot inject unsupported types or cyclic references into serialized data.
   - Internal sets and frozensets contain strictly string elements and are deterministically serialized via standard lexicographical sorting (`sorted(obj)`), producing a clean `list[str]` without complex sort keys or collision risks.
   - UUIDs are converted to `str`, and Enums are converted to their declared `.value`.

---

### 13.5. Capability Permission Ownership & Registration Flow

#### Static Capability Enumeration
Capabilities are not arbitrary strings; they are strictly enumerated in `contracts/task.py`:
```python
class Capability(str, Enum):
    DOCUMENT_PARSING = "capability.document.parse"
    ATS_SCORING = "capability.resume.ats_score"
    KEYWORD_MATCHING = "capability.text.keyword_match"
    QUESTION_STRUCTURING = "capability.interview.question_structure"
    METRIC_COMPUTATION = "capability.analytics.compute_metrics"
    BASELINE_EVALUATION = "capability.legacy.baseline_eval"
```

#### Trusted Origin of Caller Identity
Caller identity originates strictly from trusted application service code (e.g. `ResumeService`, `InterviewService`), not from user-submitted request data.
- **Input Insulation:** User request parameters, HTTP query strings, headers, and task payloads **cannot construct, pass, or override** trusted caller identity.
- **Separation of Architectural Concerns:**
  1. *Capability Enumeration:* Static declaration of authorized capabilities in `contracts/task.py` (`Capability` enum).
  2. *Handler Registration:* In-code binding of trusted Python functions to capabilities in `ModuleRegistry` during application boot.
  3. *Permission Granting:* Static assignment of permitted capability sets to calling application services in `policy/permissions.py`.
  4. *Pre-Dispatch Authorization:* Before any task is submitted to the worker pool, `ExecutionPolicy.authorize(caller_permissions, task.capability)` validates that the requested capability is explicitly permitted for that caller context.
  5. *Mandatory Default-Deny:* Any request lacking an explicit grant raises `UnauthorizedCapabilityError`.
    BASELINE_EVALUATION = "capability.legacy.baseline_eval"
```

#### Registration & Binding Lifecycle
1. **Startup Registration:** At application startup, the `ModuleRegistry` registers trusted handler functions against specific capabilities and module IDs:
   ```python
   registry.register_module(
       module_id="ats_scoring_v1",
       capability=Capability.ATS_SCORING,
       handler_callable=ats_scoring_handler,
   )
   ```
   Registration occurs once in code during backend initialization. No user request, API payload, or runtime parameter can register or alter a handler binding.
2. **Task Declaration:** A workflow DAG defines tasks statically using `TaskDefinition(task_id="score", capability=Capability.ATS_SCORING, handler="ats_scoring_v1")`.
3. **Caller Permission Evaluation:** When a service (e.g. `ResumeService`) creates an `ExecutionContext`, the calling service context determines the permitted capabilities (e.g. `DOCUMENT_PARSING`, `ATS_SCORING`, `KEYWORD_MATCHING`).
4. **Pre-Dispatch Guard:** Before dispatching any task, `ExecutionPolicy.authorize(caller_permissions, task.capability)` verifies that the requested capability is included in the caller's permitted set. If not, execution is rejected with `UnauthorizedCapabilityError`.

---

### 13.6. Additional Engineering Decisions & Refinements

#### 1. Canonical Registry Format (`models.json`)
- The authoritative model registry file is `backend/pie/registry/models.json`.
- It is parsed using Python's standard library `json` module, maintaining the **zero-new-dependency** rule for R0.
- An optional helper parses `models.yaml` only if `pyyaml` is detected in the environment; otherwise, `models.json` is always loaded.

#### 2. Exception Naming Hygiene
To prevent shadowing standard library built-ins (which causes hard-to-debug catch-block bugs and IDE confusion):
- `ModuleNotFoundError` $\rightarrow$ **`RegistryModuleNotFoundError`** (avoids shadowing Python's built-in `ModuleNotFoundError`).
- `ModelNotFoundError` $\rightarrow$ **`RegistryModelNotFoundError`**.
- `TimeoutError` $\rightarrow$ **`TaskTimeoutError`** (avoids shadowing Python's built-in `TimeoutError`).
- All PIE exceptions inherit from a common base class: `PIEException`.

#### 3. Engine Lifecycle and Per-Process Concurrency Limits
- **Exactly One Engine Instance per Gunicorn Worker Process:**
  - Gunicorn utilizes a pre-fork worker model where each worker process is an independent OS process hosting its own private Python interpreter.
  - Exactly one PIE engine instance exists per Gunicorn worker process upon explicit initialization.
  - Exactly one bounded `ThreadPoolExecutor(max_workers=4)` is owned by each engine instance.
- **Zero Creation at Module Import (Lazy Instantiation):**
  - Importing `pie` or `pie.engine` must NEVER create thread pools, instantiate engines, or allocate background threads.
  - Thread pools are created only when `engine.initialize()` is explicitly invoked during application startup.
- **Explicit Lifecycle:**
  - Initialization: `engine.initialize()` creates the bounded worker pool and verifies registry readiness.
  - Shutdown: `engine.shutdown()` stops task acceptance, cancels queued items, and releases resources.
- **Feature Flag Invariant:**
  - When `PIE_ENABLED = false` (production default), neither the engine nor the thread pool is initialized. Zero worker threads are created.
- **Concurrency Scoping:**
  - `max_workers = 4` is strictly a **per-process limit**, not a global deployment limit.
  - Global deployment concurrency is not assumed to be a fixed constant (avoiding reliance on assumed worker counts). Total cluster concurrency is dynamically $N \times 4$, where $N$ is the number of active Gunicorn worker processes configured in the runtime deployment environment.

#### 4. Granular Status Separation: StepStatus vs. WorkflowStatus
To prevent ambiguous state reporting, PIE cleanly separates task-level lifecycle from workflow-level lifecycle:
- **`StepStatus` (Individual Task):** `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`, `TIMED_OUT`.
- **`WorkflowStatus` (Consolidated DAG):**
  - `PENDING`: Graph constructed, not yet started.
  - `RUNNING`: Tasks currently executing in the engine.
  - `COMPLETED`: All tasks in the DAG completed successfully (`StepStatus.COMPLETED`).
  - `PARTIAL_SUCCESS`: Some optional or leaf tasks failed or timed out, but primary required outputs were produced.
  - `FAILED`: A critical path task failed or experienced unrecoverable error, preventing downstream execution.
  - `TIMED_OUT`: The overall workflow deadline (`deadline_mono`) expired before the graph could complete.

#### 5. Passive Health Checks
The `HealthChecker` module in `backend/pie/health/` implements strictly **passive validation**:
- Validates the internal consistency and schema of `models.json`.
- Confirms that all mandatory capabilities have at least one registered handler in `ModuleRegistry`.
- Confirms thread pool availability and memory footprint.
- **Zero active probes:** It makes zero external network calls, does not ping external LLM APIs, and executes zero database queries.

#### 6. Non-Disruptive Coexistence (`PIE_ENABLED = false`)
When `PIE_ENABLED = false` (the strict production default in R0):
- `backend/pie` is **never imported** during standard request handling or Flask boot.
- No `ThreadPoolExecutor` is created; zero background threads are spawned.
- Existing legacy routes (`/api/interview/*`, `/api/resume/*`, `/api/auth/*`) operate with 100% parity.
- The PIE health endpoint returns HTTP 404 or a disabled notice without initializing the engine.

---

### 13.7. Revised Step 3B Implementation Sequence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.1: Contracts, Immutability & Exception Hierarchy                    │
│ - Files: backend/pie/__init__.py, contracts/context.py, task.py,            │
│          results.py, exceptions.py, workflow.py                             │
│ - Enforce recursive immutability (freeze_immutable, unfreeze_to_dict)       │
│ - Defensive copying to prevent aliasing; explicit .to_dict() methods        │
│ - PIEException hierarchy (prefixed names, no built-in shadowing)            │
│ - Test: backend/tests/test_pie_contracts.py (100% unit test coverage)       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.2: Declarative Model & Module Registries                            │
│ - Files: backend/pie/registry/models.json, model_registry.py,               │
│          module_registry.py                                                 │
│ - Validate lifecycle status (baseline_only models blocked from production)  │
│ - Test: backend/tests/test_pie_registry.py (offline validation, error cases) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.3: Workflow DAG Engine & Cycle Detection                            │
│ - Files: backend/pie/workflow/dag.py, validator.py, ordering.py             │
│ - Implement 3-color DFS cycle detector & topological stage partitioner      │
│ - Test: backend/tests/test_pie_dag.py (linear, diamond, cycle paths, order) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.4: Execution Engine, Dispatcher, Result Fencing & Policy Guard      │
│ - Files: backend/pie/engine/runner.py, executor.py, dispatcher.py           │
│          backend/pie/policy/guard.py, rules.py                              │
│ - Implement result fencing with execution_tokens, timeout abandonment,      │
│   idempotency metadata (R0 timeout retries disabled), and capability auth   │
│ - Enforce pure function handlers and trusted caller identity validation     │
│ - Test: backend/tests/test_pie_engine.py & test_pie_policy.py               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3B.5: Evaluators, Passive Health Diagnostics & Integration Hook        │
│ - Files: backend/pie/evaluation/recorder.py, evaluators.py, taxonomy.py     │
│          backend/pie/health/checker.py, status.py                           │
│ - Wire optional PIE health check into main.py (guarded by PIE_ENABLED=true) │
│ - Full regression: 72 existing backend tests + all new PIE test suites      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 13.8. Comprehensive Unit and Integration Test Plan

| Test Suite | File Location | Key Verifications |
| :--- | :--- | :--- |
| **Contracts Suite** | `backend/tests/test_pie_contracts.py` | - **Deep recursive immutability:** mutating nested `MappingProxyType`, `tuple`, or `frozenset` raises `TypeError` / `AttributeError`.<br>- **Aliasing protection:** mutating caller-owned input structures (`dict`, `list`, `set`) after passing to contracts does not alter contract data.<br>- **Active call-stack cycle tracking:** genuine cyclic references ($A \to B \to A$) raise `ContractViolationError`, while diamond references / shared-reference DAGs ($A \to [B, C]$ where $B, C \to D$) are cleanly permitted.<br>- **Nested contract validation:** exact concrete-type membership (`type(obj) in APPROVED_CONTRACT_TYPES`); unregistered subclasses of `BaseContract` and duck-typed objects with `.to_dict()` are rejected with `ContractViolationError`; `.to_dict()` output is recursively re-validated through `unfreeze_to_dict()`.<br>- **Strict subclass type-check ordering:** verifies `bool` and `IntEnum` are not misidentified as primitive integers.<br>- **Payload set prohibition:** passing sets/frozensets in JSON payloads raises `ContractViolationError`.<br>- **String-only internal sets:** internal sets contain only `str` elements (`frozenset[str]`); non-string or mixed elements raise `ContractViolationError`; deterministically sorted via standard `sorted(obj)` without custom keys or reliance on `dataclasses.asdict()`.<br>- Exception hierarchy: domain exceptions carry `message` and `code` without shadowing built-ins.<br>- Status transitions: `StepStatus` and `WorkflowStatus` values. |
| **Registry Suite** | `backend/tests/test_pie_registry.py` | - Loading canonical `models.json` offline without network or credentials.<br>- Rejection of malformed schemas or invalid status codes.<br>- Rejection of production task dispatch for models marked `baseline_only`.<br>- Duplicate module registration raises `DuplicateModuleError`.<br>- Querying unregistered capability raises `RegistryModuleNotFoundError`. |
| **DAG & Ordering Suite** | `backend/tests/test_pie_dag.py` | - 3-color DFS cycle detection detects direct (A $\rightarrow$ A) and indirect (A $\rightarrow$ B $\rightarrow$ C $\rightarrow$ A) cycles.<br>- Cycle error message includes exact cycle path.<br>- Missing dependency raises `ContractViolationError`.<br>- Topological sorting stages partition tasks into correct parallelizable stages. |
| **Engine & Fencing Suite** | `backend/tests/test_pie_engine.py` | - In-process execution of independent tasks across stages.<br>- Effective timeout calculation: task deadline capped by workflow deadline.<br>- Timeout simulation: long-running mock handler times out; step marked `TIMED_OUT`.<br>- **Result fencing verification:** simulated late result arriving from abandoned thread with stale `execution_token` is discarded and does not alter coordinator workflow state.<br>- **Handler purity:** handlers execute as pure functions without mutating shared engine state or global variables.<br>- **Timeout retry invariant:** timed-out task is **never** retried in R0 (`retry_on_timeout=False` enforced engine-wide), even if `is_idempotent=True`.<br>- **ThreadPool shutdown:** `shutdown(wait=False, cancel_futures=True)` rejects new tasks, cancels queued tasks, and allows running worker threads to finish naturally. |
| **Policy Guard Suite** | `backend/tests/test_pie_policy.py` | - Default-deny: unregistered capability raises `UnauthorizedCapabilityError`.<br>- Caller permission check: service lacking capability permission is rejected.<br>- Payload safety: payload content cannot alter capability routing or construct/override caller identity. |
| **Isolation & Parity Suite** | `backend/tests/test_pie_isolation.py` | - Subprocess test: `import pie` executes with zero threads created and zero database calls.<br>- Lazy initialization: thread pool created only upon explicit `engine.initialize()`.<br>- Feature flag test: with `PIE_ENABLED=false`, zero PIE background threads or memory allocations exist.<br>- Full regression: 72 existing tests pass with 100% parity. |

---

### 13.9. Trade-offs, Operational Limitations, and Final Decisions

1. **CPython Thread Preemption Limitation:**
   - *Limitation:* Abandoned worker threads consume thread pool slots and CPU until they complete naturally; interpreter exit joins all non-daemon worker threads.
   - *Mitigation:* Bounded handler timeouts (max 15.0s, default 5.0s), handlers restricted to $O(N)$ CPU operations, result fencing to prevent corrupting state, and disabling timeout retries in R0 to prevent thread pool stampedes.
2. **Logical Authorization vs. OS Sandboxing:**
   - *Limitation:* In-process policy guards cannot prevent malicious code from executing arbitrary CPython bytecode if bad code is introduced into the repository.
   - *Mitigation:* Trusted codebase model, mandatory code review, static linting forbidding `subprocess`/raw SQL, and strict separation between untrusted input payloads and capability routing.
3. **Deep Immutability Overhead:**
   - *Limitation:* Recursive defensive copying and wrapping in `MappingProxyType` requires custom traversal rather than auto-generated dataclass constructors.
   - *Mitigation:* Defensive recursive traversal with cycle detection eliminates caller aliasing risks; wrapping nodes in `MappingProxyType` avoids third-party container overhead, while explicit `.to_dict()` provides deterministic, native JSON serialization.
4. **Canonical Registry Format:**
   - *Final Decision:* `models.json` is canonical. No external YAML library is required for R0.
5. **Strict Feature Flag Invariant:**
   - *Final Decision:* `PIE_ENABLED=false` remains the default. PIE Core is completely dormant in production until explicitly authorized and enabled by the operator.

---

### 13.10. Final Architecture Corrections and Technical Refinements (Step 3A.2)

This subsection consolidates the final engineering corrections, operational boundaries, and verification mandates established in Step 3A.2 prior to Step 3B implementation.

#### 13.10.1. Recursive Immutability, Defensive Copying & Serialization Contract
- **Problem Statement:** Standard `@dataclass(frozen=True)` provides shallow immutability. Wrapping top-level dictionaries in `MappingProxyType(dict(payload))` leaves nested collections mutable and allows mutations via retained references from the caller (aliasing). Furthermore, `dataclasses.asdict()` cannot be assumed to convert `MappingProxyType` to native JSON-serializable dictionaries reliably across Python 3.11 and 3.14.
- **Adopted Engineering Decision:**
  - Implement standard library recursive freezing via `freeze_immutable(obj)`:
    - Recursively freeze `dict` $\rightarrow$ `MappingProxyType`.
    - Recursively freeze `list` / `tuple` $\rightarrow$ `tuple`.
    - Recursively freeze `set` / `frozenset` $\rightarrow$ `frozenset[str]` (strictly string-only elements; non-string elements raise `ContractViolationError`; prohibited in JSON-bound task payloads).
    - Defensively copy all caller collections during traversal to prevent aliasing mutations.
    - Track active recursion call stack (`active_path: Set[int]`) with `try...finally` to detect genuine cycles while permitting diamond DAG references.
    - Enforce exact concrete-type membership (`type(obj) in APPROVED_CONTRACT_TYPES`); reject unregistered `BaseContract` subclasses and duck-typed objects; prevent circular imports via `@register_contract` in `contracts/base.py`.
    - Strictly order type evaluations (`bool` and `Enum` before `int`).
  - Implement an explicit serialization contract via `unfreeze_to_dict(obj)` and `.to_dict()` methods on all contract dataclasses (`ExecutionContext`, `TaskInput`, `TaskOutput`, `TaskResult`, `TaskDefinition`, `WorkflowDefinition`, `ExecutionResult`).
  - Serialize internal string sets deterministically via standard `sorted(obj)` without complex sort keys.
  - Recursively validate `.to_dict()` outputs of nested contracts.
  - Zero external dependencies introduced.

#### 13.10.2. ThreadPoolExecutor Shutdown Semantics & Interpreter Exit Reality
- **Problem Statement:** Prior drafts claimed `shutdown(wait=False, cancel_futures=True)` guarantees prompt process exit. In CPython, worker threads spawned by `ThreadPoolExecutor` are non-daemon threads; during interpreter exit, CPython's `threading` runtime joins all non-daemon threads.
- **Adopted Engineering Decision:**
  - Acknowledge that `wait=False` returns immediately to the caller and stops accepting new tasks, but **does not forcibly terminate running threads**.
  - Queued tasks are cancelled via `cancel_futures=True`, but running worker threads must finish naturally.
  - Do not claim guaranteed instantaneous interpreter termination.
  - All PIE task handlers in R0 must adhere to bounded, short-lived execution expectations: strictly $O(N)$ CPU operations with predictable latency.

#### 13.10.3. Result Fencing Boundaries, Handler Purity & Elimination of R0 Timeout Retries
- **Problem Statement:** Result fencing protects coordinator state from late results of abandoned worker threads, but cannot undo external side effects performed by handlers during execution.
- **Adopted Engineering Decision:**
  - Enforce pure function semantics: R0 task handlers accept `TaskInput` and return `TaskOutput`. They must **never** directly mutate shared workflow state, database records, or global variables.
  - Only the coordinator engine updates task and workflow status.
  - **Timeout retries are strictly disabled for all R0 execution:** `retry_on_timeout = False` is enforced engine-wide across all tasks.
  - Idempotency metadata (`is_idempotent: bool`) is retained in `TaskDefinition` solely for schema forward-compatibility with future milestones, but is not used to enable timeout retries in R0.
  - Stale execution tokens can never publish late results or trigger downstream execution.

#### 13.10.4. Engine Lifecycle, Lazy Instantiation & Per-Process Concurrency Scoping
- **Problem Statement:** Module-level instantiation of executors can spawn threads at import time. Assuming a fixed number of Gunicorn workers (e.g. 6) creates brittle concurrency claims.
- **Adopted Engineering Decision:**
  - Exactly one engine instance per Gunicorn worker process.
  - Exactly one bounded `ThreadPoolExecutor(max_workers=4)` per engine instance.
  - Lazy initialization: zero thread pools or background threads created on `import pie`.
  - Explicit lifecycle methods: `engine.initialize()` and `engine.shutdown()`.
  - Zero initialization when `PIE_ENABLED=false`.
  - Clarified that `max_workers=4` is strictly a per-process limit; cluster-wide concurrency is dynamically $N \times 4$.

#### 13.10.5. Trusted Caller Identity & Capability Authorization Flow
- **Problem Statement:** Potential risk of client request parameters or task payloads spoofing or elevating capability permissions.
- **Adopted Engineering Decision:**
  - Caller identity and permitted capabilities are established strictly by trusted backend service code (e.g. `ResumeService`), never from user request parameters or task payloads.
  - Strict separation between capability enumeration, handler registration, and permission granting.
  - Pre-dispatch authorization evaluates permissions before any task is submitted to the thread pool.
  - Default-deny is mandatory: unregistered capabilities or unpermitted callers immediately raise `UnauthorizedCapabilityError`.

#### 13.10.6. Additional Unit and Integration Test Mandates
- **Contract Tests (`test_pie_contracts.py`):**
  - Verify recursive immutability: attempting to mutate nested dicts, lists, or sets raises `TypeError` or `AttributeError`.
  - Verify aliasing protection: mutating caller-owned input dictionaries/lists after passing them to contracts does not alter the contract data.
  - Verify serialization: `.to_dict()` recursively returns native `dict` and `list` instances matching JSON serialization requirements.
- **Engine Tests (`test_pie_engine.py`):**
  - Verify handler purity: mock handlers do not mutate external state.
  - Verify timeout retry disabling: timed-out task is not retried even if `is_idempotent=True`.
  - Verify result fencing: late result with stale execution token is dropped without mutating coordinator state.
  - Verify shutdown: calling `shutdown(wait=False, cancel_futures=True)` cancels queued tasks and rejects new submissions.
- **Lifecycle & Isolation Tests (`test_pie_isolation.py`):**
  - Subprocess test: `import pie` executes with zero threads created and zero database connections.
  - Engine lazy initialization: thread pool created only upon explicit `engine.initialize()`.

---

### 13.11. Final Specification Consistency Pass & Architectural Hardening (Step 3A.3)

This subsection finalizes the authoritative specification reconciliation performed in Step 3A.3 to eliminate all legacy contradictions across the design document.

#### 13.11.1. Explicit Supported-Value Contract & Cycle Detection
- **Supported Values in Contracts:**
  - Primitives: strictly `str`, `int`, finite `float` (`math.isfinite(x)`: rejects `inf`, `-inf`, `nan`), `bool`, and `None`.
  - Identifiers & Enums: `uuid.UUID` (converted to string on serialization) and `enum.Enum` (serialized via declared `.value`).
  - Mappings: `dict` and `MappingProxyType`. **Keys must be strings (`str`)**. Values are recursively frozen. Non-string keys raise `ContractViolationError`.
  - Sequences: `list` and `tuple` are recursively frozen into immutable `tuple`.
  - Sets: `set` and `frozenset` are strictly string-only, frozen into `frozenset[str]`. Permitted for internal contract metadata; prohibited in JSON-bound task payloads.
  - Approved Contracts: objects whose exact concrete type is registered in `APPROVED_CONTRACT_TYPES`. Duck typing and unregistered subclasses are strictly rejected.
  - **Unsupported Types Rejected:** Custom class instances, mutable dataclasses, generators, lambdas, unregistered `BaseContract` subclasses, and non-contract objects are strictly rejected with `ContractViolationError`.
- **Cycle Detection:**
  - Ingestion and serialization algorithms track active container `id(obj)` values on the call stack via `active_path: Set[int]` with `try...finally`.
  - Genuine cycles ($A \to B \to A$) raise `ContractViolationError("Cyclic reference detected")`, while shared-reference DAGs (diamond references $A \to [B, C]$ where $B, C \to D$) are cleanly permitted.
- **Deterministic Serialization Contract:**
  - All contracts implement an explicit `.to_dict()` method powered by `unfreeze_to_dict(obj)`.
  - Internal string sets and frozensets are deterministically serialized via standard lexicographical string sorting (`sorted(obj)`).
  - **`dataclasses.asdict()` is strictly forbidden** for contract serialization due to inconsistent handling of `MappingProxyType` and custom immutability wrappers across Python versions.

#### 13.11.2. Absolute Prohibition of Timeout Retries in R0
- **Universal Rule:** Timeout retries are **strictly prohibited engine-wide for every R0 task**.
- `retry_on_timeout` is unconditionally forced to `False` in `TaskDefinition`.
- `is_idempotent` is retained solely as future-facing metadata.
- A timed-out task unconditionally transitions directly and permanently to `StepStatus.TIMED_OUT`. No timeout retry is permitted under any circumstances, even if `is_idempotent = True`.
- **Ordinary Non-Timeout Retries:** Only transient resource contention errors (such as thread pool submission failure or temporary lock wait) on tasks explicitly declared with `is_idempotent = True` are eligible for bounded retry up to `max_retries <= 2`.

#### 13.11.3. Reconciled Shutdown Semantics
- Calling `executor.shutdown(wait=False, cancel_futures=True)` stops accepting new tasks and cancels unstarted queued tasks, returning immediately to the caller.
- Worker threads spawned by `ThreadPoolExecutor` are non-daemon. Running workers **cannot be forcibly terminated** and must finish naturally.
- CPython interpreter exit may wait for active non-daemon threads.
- No guaranteed immediate process termination is claimed.
- All R0 handlers must adhere to bounded $O(N)$ CPU execution expectations.

#### 13.11.4. Monotonic Elapsed-Time Workflow Deadlines
- Workflow deadlines are elapsed-time budgets calculated and checked strictly using a monotonic clock (`time.monotonic()`).
- `ExecutionContext` computes `deadline_mono = time.monotonic() + timeout_seconds`.
- Effective timeout: $\min(\text{task.timeout\_seconds}, \max(0.0, \text{context.deadline\_mono} - \text{time.monotonic()}))$.
- Immune to system clock adjustments, NTP time steps, and wall-clock shifts. No distributed clock synchronization semantics are assumed.

#### 13.11.5. Handler Purity & State Mutation Ownership
- Handlers in R0 are pure functions: `TaskInput -> TaskOutput`.
- Handlers must not perform database writes, filesystem writes, network calls, global mutations, or direct workflow state mutations.
- Only the coordinator engine may mutate workflow execution state (`task_results`, `StepStatus`, `WorkflowStatus`).

---

### 13.12. Contract Edge-Case Hardening & Approved Type Allowlist (Step 3A.5)

This subsection consolidates the contract edge-case resolutions established in Step 3A.4 and Step 3A.5:

#### 13.12.1. Exact Approved Contract Type Enforcement & Allowlist Model
- **Exact Concrete-Type Membership:** Contract validation strictly checks `type(obj) in APPROVED_CONTRACT_TYPES` (via `is_approved_contract(obj)`). Checking `isinstance(obj, BaseContract)` is rejected because it permits unapproved arbitrary subclasses.
- **Unregistered Subclass Rejection:** An unapproved subclass inheriting from `BaseContract` is strictly rejected with `ContractViolationError`. Inheritance alone does not grant admission to the contract boundary.
- **Duck-Typing Rejection:** Checking `hasattr(obj, "to_dict")` is strictly prohibited.
- **Acyclic Import Architecture:** To prevent circular imports between `contracts/base.py` and concrete contract modules (`context.py`, `task.py`, `results.py`, `workflow.py`), `base.py` defines a thread-safe registry `_APPROVED_CONTRACT_CLASSES: Set[type] = set()` and a `@register_contract` decorator. Concrete contract modules import and apply `@register_contract` upon declaration. `base.py` never imports concrete contract modules.
- **Recursive Validation on Serialization:** When `unfreeze_to_dict()` serializes an approved contract object, the dictionary returned by `obj.to_dict()` is recursively passed back into `unfreeze_to_dict(raw_dict, active_path)` under the exact same supported-value restrictions.

#### 13.12.2. Active Call-Stack Cycle Detection & Aliasing Semantics
- **Active Path Tracking:** Cycle detection tracks the **current recursion call stack** (`active_path: Set[int]`), NOT every object ever visited.
- **Stack Protocol:** An object ID is added to `active_path` upon entering container traversal and removed in a `finally` block upon exit (guaranteeing removal even on exceptional exits).
- **Cycle vs DAG Distinction:**
  - *Genuine Cyclic Reference ($A \to B \to A$ or self-reference):* When child $B$ points back to ancestor $A$, `id(A)` is already present in `active_path`, raising `ContractViolationError("Cyclic reference detected")`.
  - *Shared-Reference DAG / Diamond Reference ($A \to [B, C]$ where both $B \to D$ and $C \to D$):* Container $D$ is traversed and removed from `active_path` during the processing of branch $B$. When branch $C$ subsequently traverses $D$, `id(D)` is no longer in `active_path`. Traversal succeeds cleanly without false positives.
- **Aliasing Protection via Defensive Copying:** When caller-owned mutable containers (`dict`, `list`, `set`) are frozen, fresh immutable containers (`MappingProxyType`, `tuple`, `frozenset`) are constructed. Subsequent mutations by the caller to the original objects cannot alter contract data.

#### 13.12.3. Deterministic Set Serialization, Payload Set Prohibition & Type-Check Ordering
- **JSON Payload Set Prohibition:** Sets and frozensets are **strictly prohibited** in JSON-bound task payloads (`TaskInput.payload`, `TaskOutput.data`, `ExecutionResult.task_results`). JSON specifications (RFC 8259) have no native set construct. Callers must provide ordered lists or tuples. Attempting to pass a `set` or `frozenset` inside a payload dictionary raises `ContractViolationError`.
- **Contract Metadata Sets:** Sets and frozensets are retained strictly for internal contract metadata (e.g. `TaskDefinition.dependencies: frozenset[str]`), DAG validation algorithms, and capability permission sets.
- **String-Only Internal Sets & Lexicographical Sorting:** In R0, internal sets and frozensets (used for contract metadata such as `TaskDefinition.depends_on`) may contain **only strings (`str`)**. They are frozen into `frozenset[str]`. Heterogeneous sets or sets containing non-string items (e.g. `int`, `float`, objects) are strictly rejected with `ContractViolationError`. Serialization simply uses standard `sorted(obj)`, producing a deterministic `list[str]` with zero collision risk. Custom compound sort keys and claims of universal multi-type canonical ordering are eliminated.
- **Strict Subclass Type-Check Ordering:** In Python, `issubclass(bool, int)` and `issubclass(IntEnum, int)` are True. To prevent `bool` and `IntEnum` instances from being evaluated as primitive integers, type evaluations must strictly check `bool` and `Enum` before `int`.

#### 13.12.4. Remaining Operational Limitations
- **CPython Non-Daemon Thread Exit:** As established in Step 3A.2/3A.3, worker threads spawned by `ThreadPoolExecutor` cannot be forcibly terminated. Handlers must be short-lived, $O(N)$ CPU operations.
- **Process-Local Rate Limiting & Concurrency:** Execution and rate limiting remain process-local within each Gunicorn worker; multi-worker coordination is deferred to future milestones.
- **Zero External Dependencies:** Standard library only; no Pydantic, Pyrsistent, or PyYAML requirements in `requirements.txt`.
- **Static In-Process Schema:** R0 contracts are strictly statically typed in-process dataclasses, matching the approved Step 3A/3B scope.

---

**END OF REVISED DESIGN DOCUMENT — STEP 3A.5 COMPLETE. AWAITING OPERATOR APPROVAL PRIOR TO STEP 3B IMPLEMENTATION.**

