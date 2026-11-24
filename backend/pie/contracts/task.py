"""
task.py — Task Contracts & Definitions
=====================================
Defines Capability, ProvenanceType, TaskInput, TaskOutput, and TaskDefinition.
Implements payload freezing (sets prohibited), caller aliasing protection,
and strict timeout retry invariants (retry_on_timeout=False enforced).
"""

import math
from enum import Enum
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Dict, Any, Optional, Tuple, Sequence

from .base import BaseContract, register_contract, freeze_immutable, unfreeze_to_dict
from .context import ExecutionContext
from .exceptions import ContractViolationError


class Capability(str, Enum):
    """Enumeration of all statically authorized capabilities within PIE."""
    DOCUMENT_PARSING = "capability.document.parse"
    ATS_SCORING = "capability.resume.ats_score"
    KEYWORD_MATCHING = "capability.text.keyword_match"
    QUESTION_STRUCTURING = "capability.interview.question_structure"
    METRIC_COMPUTATION = "capability.analytics.compute_metrics"
    BASELINE_EVALUATION = "capability.legacy.baseline_eval"


class ProvenanceType(str, Enum):
    """Origin of data produced by a task."""
    OBSERVED = "observed"    # Deterministic measurement, regex extraction, direct parser output
    PREDICTED = "predicted"  # Output of statistical ML classifier or heuristic algorithm
    INFERRED = "inferred"    # Multi-factor algorithmic deduction or legacy baseline synthesis


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
        if not isinstance(capability, Capability):
            raise ContractViolationError(
                f"capability must be an instance of Capability enum, got {type(capability).__name__}"
            )
        if type(context) is not ExecutionContext:
            raise ContractViolationError(
                f"context must be an exact ExecutionContext instance, got {type(context).__name__}"
            )

        object.__setattr__(self, "capability", capability)
        # JSON-bound payload disallows sets/frozensets; callers must supply ordered sequences
        object.__setattr__(self, "payload", freeze_immutable(payload, allow_sets=False))
        object.__setattr__(self, "context", context)
        object.__setattr__(
            self,
            "config_overrides",
            freeze_immutable(config_overrides or {}, allow_sets=False),
        )

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
        if not isinstance(provenance, ProvenanceType):
            raise ContractViolationError(
                f"provenance must be an instance of ProvenanceType enum, got {type(provenance).__name__}"
            )

        # JSON-bound data disallows sets/frozensets; callers must supply ordered sequences
        object.__setattr__(self, "data", freeze_immutable(data, allow_sets=False))
        object.__setattr__(self, "provenance", provenance)

        if confidence is not None:
            conf = float(confidence)
            if not (0.0 <= conf <= 1.0):
                raise ContractViolationError(f"confidence must be between 0.0 and 1.0, got {conf}")
            object.__setattr__(self, "confidence", conf)
        else:
            object.__setattr__(self, "confidence", None)

        object.__setattr__(self, "warnings", tuple(str(w) for w in (warnings or ())))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": unfreeze_to_dict(self.data),
            "provenance": self.provenance.value,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


@register_contract
@dataclass(frozen=True)
class TaskDefinition(BaseContract):
    """Static declarative definition of a single task in a workflow DAG (recursively frozen)."""
    task_id: str
    capability: Capability
    handler: str
    depends_on: Tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 5.0
    max_retries: int = 0
    backoff_factor: float = 0.5
    is_idempotent: bool = False
    retry_on_timeout: bool = False

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

