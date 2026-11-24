"""
results.py — Execution Outcome & Result Contracts
================================================
Defines TaskResult and ExecutionResult contracts.
Implements result fencing tokens, latency measurements, and consolidated workflow reporting.
"""

import uuid
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Dict, Any, Optional, Tuple, Sequence

from .base import BaseContract, register_contract, freeze_immutable, unfreeze_to_dict
from .task import Capability, TaskOutput
from .workflow import StepStatus, WorkflowStatus
from .exceptions import ContractViolationError


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

    def __init__(
        self,
        task_id: str,
        capability: Capability,
        status: StepStatus,
        output: Optional[TaskOutput] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        latency_ms: float = 0.0,
        retry_count: int = 0,
        execution_token: Optional[str] = None,
    ):
        if not isinstance(capability, Capability):
            raise ContractViolationError(
                f"capability must be an instance of Capability enum, got {type(capability).__name__}"
            )
        if not isinstance(status, StepStatus):
            raise ContractViolationError(
                f"status must be an instance of StepStatus enum, got {type(status).__name__}"
            )
        if output is not None and type(output) is not TaskOutput:
            raise ContractViolationError(
                f"output must be an exact TaskOutput instance or None, got {type(output).__name__}"
            )

        object.__setattr__(self, "task_id", str(task_id))
        object.__setattr__(self, "capability", capability)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "output", output)
        object.__setattr__(self, "error_message", str(error_message) if error_message is not None else None)
        object.__setattr__(self, "error_code", str(error_code) if error_code is not None else None)
        object.__setattr__(self, "latency_ms", max(0.0, float(latency_ms)))
        object.__setattr__(self, "retry_count", max(0, int(retry_count)))
        object.__setattr__(
            self,
            "execution_token",
            str(execution_token) if execution_token else str(uuid.uuid4()),
        )

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
        if not isinstance(status, WorkflowStatus):
            raise ContractViolationError(
                f"status must be an instance of WorkflowStatus enum, got {type(status).__name__}"
            )
        if not isinstance(task_results, (dict, MappingProxyType)):
            raise ContractViolationError("task_results must be a mapping of task_id -> TaskResult.")

        for tid, res in task_results.items():
            if not isinstance(tid, str):
                raise ContractViolationError(f"task_results key must be str, got {type(tid).__name__}")
            if type(res) is not TaskResult:
                raise ContractViolationError(
                    f"task_results value for '{tid}' must be an exact TaskResult instance, got {type(res).__name__}"
                )
            if tid != res.task_id:
                raise ContractViolationError(
                    f"task_results key '{tid}' does not match TaskResult.task_id '{res.task_id}'"
                )

        object.__setattr__(self, "trace_id", str(trace_id))
        object.__setattr__(self, "workflow_id", str(workflow_id))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "task_results", freeze_immutable(task_results, allow_sets=False))
        object.__setattr__(self, "total_latency_ms", max(0.0, float(total_latency_ms)))
        object.__setattr__(self, "errors", tuple(str(e) for e in (errors or ())))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "task_results": unfreeze_to_dict(self.task_results),
            "total_latency_ms": self.total_latency_ms,
            "errors": list(self.errors),
        }

