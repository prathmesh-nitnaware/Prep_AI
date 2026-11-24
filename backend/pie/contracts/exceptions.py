"""
exceptions.py — Domain Exception Hierarchy for PIE Core
======================================================
Defines domain exceptions with structured error codes and messages.
Prefixed naming prevents shadowing Python built-in exceptions.
"""

from typing import Sequence, Optional


class PIEException(Exception):
    """Base exception for all PIE domain errors."""
    def __init__(self, message: str, code: str = "PIE_INTERNAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ContractViolationError(PIEException):
    """Raised when a data structure or object fails contract validation or immutability rules."""
    def __init__(self, message: str):
        super().__init__(message, "CONTRACT_VIOLATION")


class PolicyViolationError(PIEException):
    """Raised when an operation violates security policy (e.g. raw SQL, unauthorized subprocess)."""
    def __init__(self, message: str):
        super().__init__(message, "POLICY_VIOLATION")


class UnauthorizedCapabilityError(PIEException):
    """Raised when a task requests a capability not granted to the caller context."""
    def __init__(self, capability: str):
        super().__init__(f"Capability '{capability}' is unauthorized.", "UNAUTHORIZED_CAPABILITY")
        self.capability = capability


class WorkflowCycleError(PIEException):
    """Raised when a circular dependency cycle is detected in a workflow DAG."""
    def __init__(self, cycle_path: Sequence[str]):
        super().__init__(f"Cyclic dependency detected: {' -> '.join(cycle_path)}", "WORKFLOW_CYCLE")
        self.cycle_path = tuple(cycle_path)


class TaskTimeoutError(PIEException):
    """Raised when a task exceeds its configured execution deadline."""
    def __init__(self, task_id: str, timeout_sec: float):
        super().__init__(f"Task '{task_id}' exceeded timeout of {timeout_sec}s", "TASK_TIMEOUT")
        self.task_id = task_id
        self.timeout_sec = timeout_sec


class RegistryModuleNotFoundError(PIEException):
    """Raised when a module is missing from ModuleRegistry (avoids shadowing built-in ModuleNotFoundError)."""
    def __init__(self, module_id: str):
        super().__init__(f"Module '{module_id}' not found in registry.", "MODULE_NOT_FOUND")
        self.module_id = module_id


class RegistryModelNotFoundError(PIEException):
    """Raised when a model identifier is missing from ModelRegistry."""
    def __init__(self, model_id: str):
        super().__init__(f"Model '{model_id}' not found in registry.", "MODEL_NOT_FOUND")
        self.model_id = model_id

