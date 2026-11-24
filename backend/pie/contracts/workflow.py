"""
workflow.py — Workflow Lifecycle & Definition Contracts
======================================================
Defines StepStatus, WorkflowStatus, and WorkflowDefinition.
Provides immutable DAG representation with task allowlisting.
"""

import math
from enum import Enum
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Any

from .base import BaseContract, register_contract, freeze_immutable, unfreeze_to_dict
from .task import TaskDefinition
from .exceptions import ContractViolationError


class StepStatus(str, Enum):
    """Execution lifecycle status of an individual task step in a DAG."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class WorkflowStatus(str, Enum):
    """Consolidated execution status of an entire workflow DAG."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


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

