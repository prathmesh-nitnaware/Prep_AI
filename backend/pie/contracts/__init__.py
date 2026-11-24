"""
PIE Contracts Package.
Exports all approved contract types, enums, exception classes, and utility functions.
Automatically seals the contract registry on import.
"""

from .exceptions import (
    PIEException,
    ContractViolationError,
    PolicyViolationError,
    UnauthorizedCapabilityError,
    WorkflowCycleError,
    TaskTimeoutError,
    RegistryModuleNotFoundError,
    RegistryModelNotFoundError,
)
from .base import (
    BaseContract,
    register_contract,
    seal_registry,
    is_registry_sealed,
    is_approved_contract,
    get_approved_contract_types,
    APPROVED_CONTRACT_TYPES,
    freeze_immutable,
    unfreeze_to_dict,
)
from .context import ExecutionContext
from .task import (
    Capability,
    ProvenanceType,
    TaskInput,
    TaskOutput,
    TaskDefinition,
)
from .workflow import (
    StepStatus,
    WorkflowStatus,
    WorkflowDefinition,
)
from .results import (
    TaskResult,
    ExecutionResult,
)

# Seal the registry automatically upon package import
_sealed_types = seal_registry()

# Enforce exact concrete-type contract allowlist of length 7
_EXPECTED_CONTRACT_TYPES = (
    ExecutionContext,
    ExecutionResult,
    TaskDefinition,
    TaskInput,
    TaskOutput,
    TaskResult,
    WorkflowDefinition,
)

assert len(get_approved_contract_types()) == 7, (
    f"Expected exactly 7 approved contract types, found {len(get_approved_contract_types())}"
)
assert get_approved_contract_types() == _EXPECTED_CONTRACT_TYPES, (
    f"Registry types mismatch: {get_approved_contract_types()} vs {_EXPECTED_CONTRACT_TYPES}"
)

# Update local reference to sealed tuple
APPROVED_CONTRACT_TYPES = get_approved_contract_types()

__all__ = [
    # Exceptions
    "PIEException",
    "ContractViolationError",
    "PolicyViolationError",
    "UnauthorizedCapabilityError",
    "WorkflowCycleError",
    "TaskTimeoutError",
    "RegistryModuleNotFoundError",
    "RegistryModelNotFoundError",
    # Base & Registry
    "BaseContract",
    "register_contract",
    "seal_registry",
    "is_registry_sealed",
    "is_approved_contract",
    "get_approved_contract_types",
    "APPROVED_CONTRACT_TYPES",
    "freeze_immutable",
    "unfreeze_to_dict",
    # Context
    "ExecutionContext",
    # Task Contracts & Enums
    "Capability",
    "ProvenanceType",
    "TaskInput",
    "TaskOutput",
    "TaskDefinition",
    # Workflow Contracts & Enums
    "StepStatus",
    "WorkflowStatus",
    "WorkflowDefinition",
    # Result Contracts
    "TaskResult",
    "ExecutionResult",
]

