"""
context.py — Execution Context Contract
======================================
Defines ExecutionContext: immutable contextual metadata propagated across workflow execution.
Implements monotonic deadline calculations, aliasing-safe metadata, and registered contract typing.
"""

import math
import time
import uuid
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Dict, Any, Optional

from .base import BaseContract, register_contract, freeze_immutable, unfreeze_to_dict
from .exceptions import ContractViolationError


@register_contract
@dataclass(frozen=True)
class ExecutionContext(BaseContract):
    """
    Immutable contextual metadata propagated across workflow execution.
    - deadline_mono: monotonic clock deadline immune to wall-clock shifts and NTP steps.
    - metadata: recursively frozen MappingProxyType with caller aliasing protection.
    """
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
        object.__setattr__(self, "trace_id", str(trace_id) if trace_id else str(uuid.uuid4()))
        object.__setattr__(self, "request_id", str(request_id) if request_id else str(uuid.uuid4()))
        object.__setattr__(self, "user_id", str(user_id) if user_id is not None else None)
        object.__setattr__(self, "session_id", str(session_id) if session_id is not None else None)

        # Monotonic deadline calculation (immune to NTP adjustments or wall-clock shifts)
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
        object.__setattr__(self, "environment", str(environment))
        object.__setattr__(
            self,
            "metadata",
            freeze_immutable(metadata or {}, allow_sets=False),
        )

    def is_expired(self) -> bool:
        """Returns True if the monotonic deadline has elapsed."""
        if self.deadline_mono is None:
            return False
        return time.monotonic() > self.deadline_mono

    def remaining_seconds(self) -> Optional[float]:
        """Returns remaining seconds until monotonic deadline, or None if uncapped."""
        if self.deadline_mono is None:
            return None
        return max(0.0, self.deadline_mono - time.monotonic())

    def to_dict(self) -> Dict[str, Any]:
        """Explicit deterministic serialization without relying on dataclasses.asdict()."""
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

