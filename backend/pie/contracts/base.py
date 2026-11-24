"""
base.py — Base Contract, Approved Registry & Immutability Engine
================================================================
Implements:
1. BaseContract abstract class.
2. Sealed approved-contract allowlist registry (exact concrete-type enforcement).
3. Recursive defensive copying and freezing into standard-library immutable types.
4. Active call-stack cycle detection (try/finally) permitting shared-reference DAGs.
5. Deterministic serialization via unfreeze_to_dict with sorted string sets.
6. Strict type evaluation order (bool and Enum before int).
"""

import math
import uuid
from enum import Enum
from types import MappingProxyType
from typing import Dict, Any, Optional, Tuple, Set

from .exceptions import ContractViolationError


class BaseContract:
    """
    Abstract base class for all approved PIE contracts.
    Subclasses must be registered via @register_contract prior to registry sealing.
    Unregistered subclasses or duck-typed objects are strictly rejected.
    """
    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses of BaseContract must implement .to_dict()")


# ── REGISTRY STATE & LIFECYCLE ──
_APPROVED_CONTRACT_CLASSES: Set[type] = set()
_IS_SEALED: bool = False
APPROVED_CONTRACT_TYPES: Tuple[type, ...] = ()


def register_contract(cls: type) -> type:
    """
    Class decorator that registers a concrete contract class in the approved allowlist.
    Must be called during module import prior to seal_registry().
    """
    global _IS_SEALED
    if _IS_SEALED:
        raise ContractViolationError(
            f"Cannot register contract class '{cls.__name__}': registry is already sealed."
        )
    if not isinstance(cls, type) or not issubclass(cls, BaseContract):
        raise ContractViolationError(
            f"Registered class '{getattr(cls, '__name__', str(cls))}' must be a subclass of BaseContract."
        )
    _APPROVED_CONTRACT_CLASSES.add(cls)
    return cls


def seal_registry() -> Tuple[type, ...]:
    """
    Seals the approved contract registry, producing an immutable snapshot tuple.
    Once sealed, no further classes can be registered at runtime.
    """
    global _IS_SEALED, APPROVED_CONTRACT_TYPES
    if not _IS_SEALED:
        APPROVED_CONTRACT_TYPES = tuple(
            sorted(_APPROVED_CONTRACT_CLASSES, key=lambda c: c.__name__)
        )
        _IS_SEALED = True
    return APPROVED_CONTRACT_TYPES


def is_registry_sealed() -> bool:
    """Returns True if the contract registry is sealed against new registrations."""
    return _IS_SEALED


def is_approved_contract(obj: Any) -> bool:
    """
    Enforces exact concrete-type membership against the sealed approved contract allowlist.
    Returns False for unapproved classes even if they inherit from BaseContract.
    """
    return type(obj) in APPROVED_CONTRACT_TYPES


def get_approved_contract_types() -> Tuple[type, ...]:
    """Returns the immutable snapshot tuple of approved contract classes."""
    return APPROVED_CONTRACT_TYPES


# ── IMMUTABILITY & DEFENSIVE FREEZING ──

def freeze_immutable(
    obj: Any,
    active_path: Optional[Set[int]] = None,
    allow_sets: bool = True,
) -> Any:
    """
    Recursively and defensively freezes supported data structures into immutable standard-library representations.
    - Dicts are defensively copied into MappingProxyType (keys must be strings).
    - Lists and tuples are defensively copied into tuples.
    - Sets/frozensets are permitted only for internal metadata (allow_sets=True) and must contain exclusively strings.
    - JSON-bound payloads (allow_sets=False) strictly prohibit sets/frozensets.
    - Primitives, UUIDs, Enums, and approved contract types are preserved.
    - Non-finite floats (inf, -inf, nan) and unsupported objects raise ContractViolationError.
    - Tracks active call stack via active_path to detect genuine cycles while permitting shared-reference DAGs.
    """
    if active_path is None:
        active_path = set()

    # ── STRICT SUBCLASS TYPE-CHECK ORDERING ──
    # 1. NoneType
    if obj is None:
        return None

    # 2. Boolean (MUST precede int because issubclass(bool, int) is True)
    if isinstance(obj, bool):
        return obj

    # 3. Enum (MUST precede int because issubclass(IntEnum, int) is True)
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

    # 8. Approved Contract (exact concrete-type membership; unregistered subclasses rejected)
    if is_approved_contract(obj):
        return obj

    # ── CONTAINER RECURSION WITH ACTIVE CALL-STACK CYCLE TRACKING ──
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

        # 12. Unsupported types rejected (unregistered BaseContract subclasses, duck-typed objects, etc.)
        raise ContractViolationError(
            f"Unsupported type '{type(obj).__name__}' cannot be made immutable. "
            "Only primitives (str, int, finite float, bool, None), UUIDs, Enums, approved contract types, "
            "and nested dicts/lists/string-frozensets of these types are permitted in task contracts."
        )
    finally:
        active_path.remove(obj_id)


# ── DETERMINISTIC SERIALIZATION ──

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

    # ── STRICT SUBCLASS TYPE-CHECK ORDERING ──
    # 1. NoneType
    if obj is None:
        return None

    # 2. Boolean (must precede int)
    if isinstance(obj, bool):
        return obj

    # 3. Enum (must precede int; extracts declared .value)
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

    # ── CONTAINER / CONTRACT RECURSION WITH ACTIVE CALL-STACK CYCLE TRACKING ──
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
            for item in obj:
                if not isinstance(item, str):
                    raise ContractViolationError(
                        f"Cannot serialize non-string set element '{item}' of type {type(item).__name__}."
                    )
            return sorted(obj)

        raise ContractViolationError(f"Cannot serialize unsupported type '{type(obj).__name__}' to JSON.")
    finally:
        active_path.remove(obj_id)

