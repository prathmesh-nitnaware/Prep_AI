"""
Unit tests for PIE Core Contracts (Step 3B.1 & 3B.1.2).
Validates:
1. Exact concrete-type allowlist membership (length 7).
2. Registry sealing & rejection of late registration.
3. Rejection of unapproved BaseContract subclasses and duck-typed objects.
4. Recursive immutability, defensive copying, and MappingProxyType enforcement.
5. Active call-stack cycle detection (prohibits cycles, permits shared-reference DAGs).
6. Strict subclass type evaluation order (bool and Enum before int).
7. String-only set rules (permitted in metadata, prohibited in JSON payloads).
8. Supported primitives, UUIDs, enums, and non-finite float rejection.
9. Contract-specific invariants:
   - ExecutionContext: monotonic clock, bounds (0.0, 300.0], rejection of zero/neg/overflow/non-finite.
   - ProvenanceType: exact approved values (OBSERVED, PREDICTED, INFERRED), rejection of obsolete values.
   - TaskInput: exact concrete ExecutionContext validation, rejection of unregistered subclasses & duck typing.
   - TaskDefinition: timeout validation (rejection of zero/neg/non-finite, clamping to 15.0s), retry_on_timeout=False.
   - WorkflowDefinition: task dictionary key matching task_id, rejection of zero/neg timeout.
   - TaskOutput: confidence bounds [0.0, 1.0], set prohibition.
   - TaskResult & ExecutionResult: key-to-task_id matching, nested contract validation, set prohibition.
10. Full serialization via .to_dict() and json.dumps() across all 7 contracts.
11. Exception class hierarchy.
"""

import json
import math
import time
import unittest
import uuid
from enum import IntEnum
from types import MappingProxyType

from backend.pie.contracts import (
    BaseContract,
    ContractViolationError,
    PolicyViolationError,
    UnauthorizedCapabilityError,
    WorkflowCycleError,
    TaskTimeoutError,
    RegistryModuleNotFoundError,
    RegistryModelNotFoundError,
    PIEException,
    register_contract,
    seal_registry,
    is_registry_sealed,
    is_approved_contract,
    get_approved_contract_types,
    APPROVED_CONTRACT_TYPES,
    freeze_immutable,
    unfreeze_to_dict,
    ExecutionContext,
    Capability,
    ProvenanceType,
    TaskInput,
    TaskOutput,
    TaskDefinition,
    StepStatus,
    WorkflowStatus,
    WorkflowDefinition,
    TaskResult,
    ExecutionResult,
)


class SampleIntEnum(IntEnum):
    ALPHA = 1
    BETA = 2


class DummyDuckTyped:
    """Implements .to_dict() but is not an approved contract."""
    def to_dict(self):
        return {"duck": "typed"}


class UnapprovedSubclass(BaseContract):
    """Subclasses BaseContract but is not registered or approved."""
    def __init__(self, value: str):
        self.value = value

    def to_dict(self):
        return {"value": self.value}


class UnregisteredContextSubclass(ExecutionContext):
    """Subclasses ExecutionContext but is not registered or approved."""
    pass


class TestPIEContracts(unittest.TestCase):

    # ─────────────────────────────────────────────────────────────
    # 1. Registry & Allowed Contract Types
    # ─────────────────────────────────────────────────────────────

    def test_registry_is_sealed_on_package_import(self):
        """Registry must be sealed automatically upon package import."""
        self.assertTrue(is_registry_sealed())

    def test_approved_contract_types_exact_membership(self):
        """Approved contract types must contain exactly the 7 canonical concrete classes."""
        types = get_approved_contract_types()
        self.assertEqual(len(types), 7)
        expected = {
            ExecutionContext,
            ExecutionResult,
            TaskDefinition,
            TaskInput,
            TaskOutput,
            TaskResult,
            WorkflowDefinition,
        }
        self.assertEqual(set(types), expected)
        self.assertEqual(tuple(sorted(types, key=lambda c: c.__name__)), APPROVED_CONTRACT_TYPES)

    def test_register_after_sealing_raises_contract_violation_error(self):
        """Calling register_contract after the registry has sealed must raise ContractViolationError."""
        class LateContract(BaseContract):
            def to_dict(self):
                return {}

        with self.assertRaises(ContractViolationError) as cm:
            register_contract(LateContract)
        self.assertIn("already sealed", str(cm.exception))

    def test_is_approved_contract_predicate(self):
        """is_approved_contract must return True only for exact concrete approved instances."""
        ctx = ExecutionContext(trace_id="t1", session_id="s1")
        self.assertTrue(is_approved_contract(ctx))

        t_in = TaskInput(capability=Capability.BASELINE_EVALUATION, payload={"k": "v"}, context=ctx)
        self.assertTrue(is_approved_contract(t_in))

        # Unapproved BaseContract subclass must return False
        unapproved = UnapprovedSubclass("test")
        self.assertFalse(is_approved_contract(unapproved))

        # Unregistered ExecutionContext subclass must return False
        unreg_ctx = UnregisteredContextSubclass(trace_id="t2")
        self.assertFalse(is_approved_contract(unreg_ctx))

        # Duck-typed object must return False
        self.assertFalse(is_approved_contract(DummyDuckTyped()))

        # Standard types must return False
        self.assertFalse(is_approved_contract({"a": 1}))
        self.assertFalse(is_approved_contract("string"))
        self.assertFalse(is_approved_contract(123))

    def test_unregistered_base_contract_subclass_rejected_by_freeze(self):
        """freeze_immutable must reject unapproved BaseContract subclasses."""
        unapproved = UnapprovedSubclass("test")
        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable(unapproved)
        self.assertIn("Unsupported type 'UnapprovedSubclass'", str(cm.exception))

    def test_duck_typed_object_rejected_by_freeze(self):
        """freeze_immutable must reject objects that merely implement .to_dict()."""
        duck = DummyDuckTyped()
        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable(duck)
        self.assertIn("Unsupported type 'DummyDuckTyped'", str(cm.exception))

    # ─────────────────────────────────────────────────────────────
    # 2. Immutability & Defensive Copying
    # ─────────────────────────────────────────────────────────────

    def test_caller_dict_mutation_does_not_affect_frozen_object(self):
        """Mutating the caller dictionary after contract creation must not modify the contract."""
        caller_dict = {"nested": {"value": 1}}
        ctx = ExecutionContext(trace_id="t1", session_id="s1")
        t_in = TaskInput(capability=Capability.BASELINE_EVALUATION, payload=caller_dict, context=ctx)

        # Mutate the caller dict
        caller_dict["nested"]["value"] = 999
        caller_dict["added"] = True

        # Contract payload must be unaffected
        self.assertEqual(t_in.payload["nested"]["value"], 1)
        self.assertNotIn("added", t_in.payload)

    def test_caller_list_mutation_does_not_affect_frozen_object(self):
        """Mutating caller list after freezing must not modify the contract internal tuple."""
        caller_list = ["a", "b"]
        caller_dict = {"items": caller_list}
        frozen = freeze_immutable(caller_dict)

        caller_list.append("c")
        self.assertEqual(frozen["items"], ("a", "b"))

    def test_caller_set_mutation_does_not_affect_frozen_set(self):
        """Mutating caller set after freezing must not modify the frozen frozenset."""
        caller_set = {"tag1", "tag2"}
        frozen = freeze_immutable(caller_set, allow_sets=True)
        self.assertIsInstance(frozen, frozenset)

        caller_set.add("tag3")
        self.assertEqual(frozen, frozenset({"tag1", "tag2"}))

    def test_frozen_mapping_proxy_type_is_read_only(self):
        """MappingProxyType elements cannot be modified, deleted, or assigned."""
        frozen = freeze_immutable({"key": "val"})
        self.assertIsInstance(frozen, MappingProxyType)
        with self.assertRaises(TypeError):
            frozen["key"] = "new_val"  # type: ignore
        with self.assertRaises(TypeError):
            del frozen["key"]  # type: ignore

    def test_frozen_dataclass_attributes_are_read_only(self):
        """Contract instances are frozen dataclasses and reject attribute assignment."""
        ctx = ExecutionContext(trace_id="t1", session_id="s1")
        with self.assertRaises((AttributeError, TypeError, Exception)):
            ctx.trace_id = "new_id"  # type: ignore

    # ─────────────────────────────────────────────────────────────
    # 3. Active Call-Stack Cycle Detection & Shared-Reference DAGs
    # ─────────────────────────────────────────────────────────────

    def test_direct_cycle_rejection(self):
        """Direct self-referential cycle must raise ContractViolationError."""
        cyclic_dict = {}
        cyclic_dict["self"] = cyclic_dict
        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable(cyclic_dict)
        self.assertIn("Cyclic reference detected", str(cm.exception))

    def test_indirect_cycle_rejection(self):
        """Indirect mutual cycle (A -> B -> A) must raise ContractViolationError."""
        a = {}
        b = {"a": a}
        a["b"] = b
        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable(a)
        self.assertIn("Cyclic reference detected", str(cm.exception))

    def test_cycle_rejection_during_serialization(self):
        """Cyclic structures encountered during unfreezing must raise ContractViolationError."""
        d = {}
        d["self"] = d
        with self.assertRaises(ContractViolationError) as cm:
            unfreeze_to_dict(d)
        self.assertIn("Cyclic reference detected during serialization", str(cm.exception))

    def test_shared_reference_dag_diamond_is_permitted(self):
        """Shared-reference DAG (diamond graph: A -> [B, C], where B and C reference D) must succeed."""
        d = {"shared_leaf": 42}
        b = {"ref_d": d, "branch": "left"}
        c = {"ref_d": d, "branch": "right"}
        root = {"b": b, "c": c}

        frozen = freeze_immutable(root)
        self.assertEqual(frozen["b"]["ref_d"]["shared_leaf"], 42)
        self.assertEqual(frozen["c"]["ref_d"]["shared_leaf"], 42)

        # Unfreezing must also succeed deterministically
        unfrozen = unfreeze_to_dict(frozen)
        self.assertEqual(unfrozen["b"]["ref_d"]["shared_leaf"], 42)
        self.assertEqual(unfrozen["c"]["ref_d"]["shared_leaf"], 42)

    # ─────────────────────────────────────────────────────────────
    # 4. Strict Subclass Type-Check Ordering & Supported Primitives
    # ─────────────────────────────────────────────────────────────

    def test_subclass_ordering_bool_preserved(self):
        """bool (a subclass of int) must be recognized as bool, not int."""
        data = {"flag_true": True, "flag_false": False}
        frozen = freeze_immutable(data)
        self.assertIs(frozen["flag_true"], True)
        self.assertIs(frozen["flag_false"], False)

        unfrozen = unfreeze_to_dict(frozen)
        self.assertIs(unfrozen["flag_true"], True)
        self.assertIs(unfrozen["flag_false"], False)

    def test_subclass_ordering_int_enum_serialized_as_value(self):
        """IntEnum (subclass of int) must be recognized as Enum and serialized to .value."""
        data = {"status": SampleIntEnum.BETA}
        frozen = freeze_immutable(data)
        self.assertEqual(frozen["status"], SampleIntEnum.BETA)

        unfrozen = unfreeze_to_dict(frozen)
        self.assertEqual(unfrozen["status"], 2)

    def test_supported_primitives_and_uuid(self):
        """None, bool, int, float, str, uuid.UUID must be supported."""
        my_uuid = uuid.uuid4()
        data = {
            "none_val": None,
            "int_val": 100,
            "float_val": 3.1415,
            "str_val": "hello",
            "uuid_val": my_uuid,
        }
        frozen = freeze_immutable(data)
        self.assertEqual(frozen["uuid_val"], my_uuid)

        unfrozen = unfreeze_to_dict(frozen)
        self.assertEqual(unfrozen["uuid_val"], str(my_uuid))
        self.assertEqual(unfrozen["float_val"], 3.1415)
        self.assertIsNone(unfrozen["none_val"])

    def test_non_finite_floats_rejected(self):
        """NaN, +inf, and -inf floats must raise ContractViolationError."""
        for bad_float in [float("nan"), float("inf"), float("-inf")]:
            with self.assertRaises(ContractViolationError) as cm:
                freeze_immutable({"val": bad_float})
            self.assertIn("Non-finite float", str(cm.exception))

    def test_non_string_dict_keys_rejected(self):
        """Dictionary keys must be strings; non-string keys raise ContractViolationError."""
        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable({123: "value"})  # type: ignore
        self.assertIn("Mapping keys must be strings", str(cm.exception))

    # ─────────────────────────────────────────────────────────────
    # 5. String-Only Sets: Metadata vs JSON Payloads
    # ─────────────────────────────────────────────────────────────

    def test_string_only_sets_permitted_in_internal_metadata(self):
        """When allow_sets=True, sets containing exclusively strings are frozen and sorted."""
        data = {"tags": {"charlie", "alpha", "bravo"}}
        frozen = freeze_immutable(data, allow_sets=True)
        self.assertIsInstance(frozen["tags"], frozenset)

        unfrozen = unfreeze_to_dict(frozen)
        self.assertEqual(unfrozen["tags"], ["alpha", "bravo", "charlie"])

    def test_sets_with_non_string_elements_rejected(self):
        """Sets containing non-string or mixed elements must raise ContractViolationError."""
        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable({"bad_set": {1, 2, 3}}, allow_sets=True)
        self.assertIn("Internal set elements must be strings", str(cm.exception))

        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable({"bad_set": {"alpha", 1}}, allow_sets=True)
        self.assertIn("Internal set elements must be strings", str(cm.exception))

    def test_sets_prohibited_in_json_payloads(self):
        """When allow_sets=False, sets and frozensets raise ContractViolationError."""
        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable({"tags": {"a", "b"}}, allow_sets=False)
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

        with self.assertRaises(ContractViolationError) as cm:
            freeze_immutable({"tags": frozenset({"a", "b"})}, allow_sets=False)
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

    def test_task_input_payload_rejects_sets_and_frozensets(self):
        """TaskInput.payload strictly prohibits sets and frozensets (direct and nested)."""
        ctx = ExecutionContext(trace_id="t1", session_id="s1")
        # Direct set
        with self.assertRaises(ContractViolationError) as cm:
            TaskInput(
                capability=Capability.BASELINE_EVALUATION,
                payload={"tags": {"eval", "qa"}},
                context=ctx,
            )
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

        # Direct frozenset
        with self.assertRaises(ContractViolationError) as cm:
            TaskInput(
                capability=Capability.BASELINE_EVALUATION,
                payload={"tags": frozenset({"eval", "qa"})},
                context=ctx,
            )
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

        # Nested frozenset
        with self.assertRaises(ContractViolationError) as cm:
            TaskInput(
                capability=Capability.BASELINE_EVALUATION,
                payload={"nested": {"inner_fset": frozenset(["x", "y"])}},
                context=ctx,
            )
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

    def test_task_output_data_rejects_sets_and_frozensets(self):
        """TaskOutput.data strictly prohibits sets and frozensets (direct and nested)."""
        # Direct set
        with self.assertRaises(ContractViolationError) as cm:
            TaskOutput(
                data={"tags": {"a", "b"}},
                provenance=ProvenanceType.PREDICTED,
            )
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

        # Direct frozenset
        with self.assertRaises(ContractViolationError) as cm:
            TaskOutput(
                data={"tags": frozenset({"a", "b"})},
                provenance=ProvenanceType.PREDICTED,
            )
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

        # Nested set
        with self.assertRaises(ContractViolationError) as cm:
            TaskOutput(
                data={"results": {"items": {"nested_set_val"}}},
                provenance=ProvenanceType.PREDICTED,
            )
        self.assertIn("Sets and frozensets are prohibited", str(cm.exception))

    def test_execution_result_task_results_rejects_sets_and_frozensets(self):
        """ExecutionResult.task_results strictly prohibits set and frozenset collections."""
        with self.assertRaises(ContractViolationError) as cm:
            ExecutionResult(
                trace_id="tr",
                workflow_id="wf",
                status=WorkflowStatus.COMPLETED,
                task_results={"item1", "item2"},  # type: ignore
                total_latency_ms=10.0,
            )
        self.assertIn("task_results must be a mapping", str(cm.exception))

        with self.assertRaises(ContractViolationError) as cm:
            ExecutionResult(
                trace_id="tr",
                workflow_id="wf",
                status=WorkflowStatus.COMPLETED,
                task_results=frozenset({"item1", "item2"}),  # type: ignore
                total_latency_ms=10.0,
            )
        self.assertIn("task_results must be a mapping", str(cm.exception))

    # ─────────────────────────────────────────────────────────────
    # 6. Contract Invariants & Property Tests
    # ─────────────────────────────────────────────────────────────

    def test_execution_context_invariants_and_timeout_bounds(self):
        """ExecutionContext monotonic clock, remaining_seconds, and (0.0, 300.0] bounds."""
        start_mono = time.monotonic()
        ctx = ExecutionContext(
            trace_id="tr-123",
            session_id="sess-456",
            timeout_seconds=10.0,
            metadata={"caller": "test"},
        )
        self.assertEqual(ctx.trace_id, "tr-123")
        self.assertEqual(ctx.session_id, "sess-456")
        self.assertEqual(ctx.timeout_seconds, 10.0)
        self.assertGreaterEqual(ctx.deadline_mono, start_mono + 9.8)
        self.assertLessEqual(ctx.deadline_mono, start_mono + 10.2)
        self.assertFalse(ctx.is_expired())
        self.assertGreater(ctx.remaining_seconds(), 0.0)
        self.assertLessEqual(ctx.remaining_seconds(), 10.0)

        # Boundary test: exactly 300.0s must succeed
        ctx_300 = ExecutionContext(trace_id="t", session_id="s", timeout_seconds=300.0)
        self.assertEqual(ctx_300.timeout_seconds, 300.0)
        self.assertIsNotNone(ctx_300.deadline_mono)

        # Rejection: zero timeout
        with self.assertRaises(ContractViolationError) as cm:
            ExecutionContext(trace_id="t", session_id="s", timeout_seconds=0.0)
        self.assertIn("timeout_seconds must be in range (0.0, 300.0]", str(cm.exception))

        # Rejection: negative timeout
        with self.assertRaises(ContractViolationError) as cm:
            ExecutionContext(trace_id="t", session_id="s", timeout_seconds=-5.0)
        self.assertIn("timeout_seconds must be in range (0.0, 300.0]", str(cm.exception))

        # Rejection: above maximum boundary (300.001 and 301.0)
        with self.assertRaises(ContractViolationError) as cm:
            ExecutionContext(trace_id="t", session_id="s", timeout_seconds=300.001)
        self.assertIn("timeout_seconds must be in range (0.0, 300.0]", str(cm.exception))

        with self.assertRaises(ContractViolationError) as cm:
            ExecutionContext(trace_id="t", session_id="s", timeout_seconds=301.0)
        self.assertIn("timeout_seconds must be in range (0.0, 300.0]", str(cm.exception))

        # Rejection: non-finite float timeout
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="t", session_id="s", timeout_seconds=float("nan"))
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="t", session_id="s", timeout_seconds=float("inf"))
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="t", session_id="s", timeout_seconds=float("-inf"))

        # Rejection: negative or non-finite deadline_mono
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="t", session_id="s", deadline_mono=-1.0)
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="t", session_id="s", deadline_mono=float("nan"))

        # Non-string metadata key rejection
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="t", session_id="s", metadata={1: "bad"})  # type: ignore

        # Serialization
        ctx_dict = ctx.to_dict()
        self.assertEqual(ctx_dict["trace_id"], "tr-123")
        self.assertEqual(ctx_dict["session_id"], "sess-456")
        self.assertEqual(ctx_dict["timeout_seconds"], 10.0)
        self.assertEqual(ctx_dict["metadata"], {"caller": "test"})

    def test_provenance_type_exact_values_and_obsolete_rejection(self):
        """ProvenanceType must support exactly OBSERVED, PREDICTED, INFERRED and reject obsolete values."""
        # Check all 3 approved values
        self.assertEqual(ProvenanceType.OBSERVED.value, "observed")
        self.assertEqual(ProvenanceType.PREDICTED.value, "predicted")
        self.assertEqual(ProvenanceType.INFERRED.value, "inferred")
        self.assertEqual(len(ProvenanceType), 3)

        # Output creation with approved values
        out_obs = TaskOutput(data={"m": 1}, provenance=ProvenanceType.OBSERVED)
        out_pred = TaskOutput(data={"m": 2}, provenance=ProvenanceType.PREDICTED)
        out_inf = TaskOutput(data={"m": 3}, provenance=ProvenanceType.INFERRED)

        self.assertEqual(out_obs.to_dict()["provenance"], "observed")
        self.assertEqual(out_pred.to_dict()["provenance"], "predicted")
        self.assertEqual(out_inf.to_dict()["provenance"], "inferred")

        # Obsolete values must be rejected
        for bad_prov in ["provenance.deterministic", "provenance.probabilistic", "deterministic", "fallback"]:
            with self.assertRaises(ContractViolationError) as cm:
                TaskOutput(data={"m": 1}, provenance=bad_prov)  # type: ignore
            self.assertIn("provenance must be an instance of ProvenanceType enum", str(cm.exception))

    def test_task_input_exact_context_type_enforcement(self):
        """TaskInput must accept exact ExecutionContext and reject unregistered subclasses & duck typing."""
        ctx = ExecutionContext(trace_id="valid-ctx")
        t_in = TaskInput(capability=Capability.BASELINE_EVALUATION, payload={"ok": True}, context=ctx)
        self.assertIs(t_in.context, ctx)

        # Unregistered subclass of ExecutionContext must be REJECTED
        unreg_ctx = UnregisteredContextSubclass(trace_id="unreg-ctx")
        with self.assertRaises(ContractViolationError) as cm:
            TaskInput(
                capability=Capability.BASELINE_EVALUATION,
                payload={"ok": True},
                context=unreg_ctx,
            )
        self.assertIn("context must be an exact ExecutionContext instance", str(cm.exception))

        # Duck-typed context must be REJECTED
        class DuckContext:
            def to_dict(self):
                return {}

        with self.assertRaises(ContractViolationError) as cm:
            TaskInput(
                capability=Capability.BASELINE_EVALUATION,
                payload={"ok": True},
                context=DuckContext(),  # type: ignore
            )
        self.assertIn("context must be an exact ExecutionContext instance", str(cm.exception))

    def test_task_definition_timeout_validation_and_invariants(self):
        """TaskDefinition timeout validation (positive/finite), cap at 15.0s, and retry invariants."""
        # Normal positive boundary
        tdef_normal = TaskDefinition(
            task_id="t_norm",
            capability=Capability.BASELINE_EVALUATION,
            handler="h_norm",
            timeout_seconds=10.0,
        )
        self.assertEqual(tdef_normal.timeout_seconds, 10.0)

        # Boundary: exactly 15.0s
        tdef_15 = TaskDefinition(
            task_id="t_15",
            capability=Capability.BASELINE_EVALUATION,
            handler="h_15",
            timeout_seconds=15.0,
        )
        self.assertEqual(tdef_15.timeout_seconds, 15.0)

        # Above maximum: clamped to 15.0s
        tdef_clamped = TaskDefinition(
            task_id="t_clamp",
            capability=Capability.BASELINE_EVALUATION,
            handler="h_clamp",
            timeout_seconds=25.0,
        )
        self.assertEqual(tdef_clamped.timeout_seconds, 15.0)

        # Rejection: zero timeout
        with self.assertRaises(ContractViolationError) as cm:
            TaskDefinition(
                task_id="t_zero",
                capability=Capability.BASELINE_EVALUATION,
                handler="h",
                timeout_seconds=0.0,
            )
        self.assertIn("timeout_seconds must be positive and finite", str(cm.exception))

        # Rejection: negative timeout
        with self.assertRaises(ContractViolationError) as cm:
            TaskDefinition(
                task_id="t_neg",
                capability=Capability.BASELINE_EVALUATION,
                handler="h",
                timeout_seconds=-5.0,
            )
        self.assertIn("timeout_seconds must be positive and finite", str(cm.exception))

        # Rejection: non-finite float timeout
        with self.assertRaises(ContractViolationError):
            TaskDefinition(
                task_id="t_nan",
                capability=Capability.BASELINE_EVALUATION,
                handler="h",
                timeout_seconds=float("nan"),
            )
        with self.assertRaises(ContractViolationError):
            TaskDefinition(
                task_id="t_inf",
                capability=Capability.BASELINE_EVALUATION,
                handler="h",
                timeout_seconds=float("inf"),
            )

        # Retry limits: clamped [0, 2]
        tdef_retries = TaskDefinition(
            task_id="t_ret",
            capability=Capability.BASELINE_EVALUATION,
            handler="h",
            max_retries=10,
            backoff_factor=0.01,
            retry_on_timeout=True,  # Must be forced False
        )
        self.assertEqual(tdef_retries.max_retries, 2)
        self.assertEqual(tdef_retries.backoff_factor, 0.1)
        self.assertFalse(tdef_retries.retry_on_timeout)

        # Empty string validations
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="", capability=Capability.BASELINE_EVALUATION, handler="h")
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="t", capability=Capability.BASELINE_EVALUATION, handler="")
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="t", capability="NOT_A_CAPABILITY", handler="h")  # type: ignore

        # Depends_on validation
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="t", capability=Capability.BASELINE_EVALUATION, handler="h", depends_on=[123])  # type: ignore

    def test_workflow_definition_invariants_and_key_matching(self):
        """WorkflowDefinition tasks validation, task_id key matching, and timeout clamp."""
        t1 = TaskDefinition(task_id="t1", capability=Capability.BASELINE_EVALUATION, handler="h1")
        wf = WorkflowDefinition(
            workflow_id="wf_1",
            tasks={"t1": t1},
            timeout_seconds=90.0,  # Clamped to 60.0
        )
        self.assertEqual(wf.workflow_id, "wf_1")
        self.assertEqual(wf.timeout_seconds, 60.0)
        self.assertEqual(len(wf.tasks), 1)

        # Rejection: task dictionary key does NOT match TaskDefinition.task_id
        t2 = TaskDefinition(task_id="task_two", capability=Capability.BASELINE_EVALUATION, handler="h2")
        with self.assertRaises(ContractViolationError) as cm:
            WorkflowDefinition(
                workflow_id="wf_mismatch",
                tasks={"mismatched_key": t2},
            )
        self.assertIn("does not match TaskDefinition.task_id", str(cm.exception))

        # Rejection: zero or negative timeout
        with self.assertRaises(ContractViolationError):
            WorkflowDefinition(workflow_id="wf_bad_to", tasks={"t1": t1}, timeout_seconds=0.0)
        with self.assertRaises(ContractViolationError):
            WorkflowDefinition(workflow_id="wf_bad_to", tasks={"t1": t1}, timeout_seconds=-10.0)

        # Empty tasks dictionary rejected
        with self.assertRaises(ContractViolationError):
            WorkflowDefinition(workflow_id="wf_empty", tasks={})

        # Non-TaskDefinition value rejected
        with self.assertRaises(ContractViolationError):
            WorkflowDefinition(workflow_id="wf_bad", tasks={"t1": "not_a_task_def"})  # type: ignore

        # Serialization
        wf_dict = wf.to_dict()
        self.assertEqual(wf_dict["workflow_id"], "wf_1")
        self.assertIn("t1", wf_dict["tasks"])
        self.assertEqual(wf_dict["tasks"]["t1"]["handler"], "h1")

    def test_timeout_boolean_rejection_across_contracts(self):
        """Boolean timeout values (True/False) must raise ContractViolationError across contracts."""
        # 1. ExecutionContext
        for b_val in [True, False]:
            with self.assertRaises(ContractViolationError) as cm:
                ExecutionContext(trace_id="t", timeout_seconds=b_val)  # type: ignore
            self.assertIn("timeout_seconds cannot be a boolean", str(cm.exception))

            with self.assertRaises(ContractViolationError) as cm:
                ExecutionContext(trace_id="t", deadline_mono=b_val)  # type: ignore
            self.assertIn("deadline_mono cannot be a boolean", str(cm.exception))

        # 2. TaskDefinition
        for b_val in [True, False]:
            with self.assertRaises(ContractViolationError) as cm:
                TaskDefinition(
                    task_id="t_b",
                    capability=Capability.BASELINE_EVALUATION,
                    handler="h_b",
                    timeout_seconds=b_val,  # type: ignore
                )
            self.assertIn("timeout_seconds cannot be a boolean", str(cm.exception))

            with self.assertRaises(ContractViolationError) as cm:
                TaskDefinition(
                    task_id="t_b",
                    capability=Capability.BASELINE_EVALUATION,
                    handler="h_b",
                    max_retries=b_val,  # type: ignore
                )
            self.assertIn("max_retries cannot be a boolean", str(cm.exception))

            with self.assertRaises(ContractViolationError) as cm:
                TaskDefinition(
                    task_id="t_b",
                    capability=Capability.BASELINE_EVALUATION,
                    handler="h_b",
                    backoff_factor=b_val,  # type: ignore
                )
            self.assertIn("backoff_factor cannot be a boolean", str(cm.exception))

        # 3. WorkflowDefinition
        t_base = TaskDefinition(task_id="t_w", capability=Capability.BASELINE_EVALUATION, handler="h")
        for b_val in [True, False]:
            with self.assertRaises(ContractViolationError) as cm:
                WorkflowDefinition(
                    workflow_id="wf_b",
                    tasks={"t_w": t_base},
                    timeout_seconds=b_val,  # type: ignore
                )
            self.assertIn("timeout_seconds cannot be a boolean", str(cm.exception))

    def test_timeout_error_normalization_across_contracts(self):
        """Invalid timeout inputs must raise ContractViolationError, never leaking raw ValueError/TypeError."""
        invalid_inputs = ["abc", "10s", "", {}, [], object()]

        # 1. ExecutionContext
        for inv in invalid_inputs:
            with self.assertRaises(ContractViolationError):
                ExecutionContext(trace_id="t", timeout_seconds=inv)  # type: ignore
            with self.assertRaises(ContractViolationError):
                ExecutionContext(trace_id="t", deadline_mono=inv)  # type: ignore

        # 2. TaskDefinition
        for inv in invalid_inputs + [None]:
            with self.assertRaises(ContractViolationError):
                TaskDefinition(
                    task_id="t_inv",
                    capability=Capability.BASELINE_EVALUATION,
                    handler="h",
                    timeout_seconds=inv,  # type: ignore
                )
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="t", capability=Capability.BASELINE_EVALUATION, handler="h", max_retries="xyz")  # type: ignore
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="t", capability=Capability.BASELINE_EVALUATION, handler="h", max_retries=None)  # type: ignore
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="t", capability=Capability.BASELINE_EVALUATION, handler="h", backoff_factor="xyz")  # type: ignore
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="t", capability=Capability.BASELINE_EVALUATION, handler="h", backoff_factor=None)  # type: ignore

        # 3. WorkflowDefinition
        t_base = TaskDefinition(task_id="t1", capability=Capability.BASELINE_EVALUATION, handler="h")
        for inv in invalid_inputs + [None]:
            with self.assertRaises(ContractViolationError):
                WorkflowDefinition(
                    workflow_id="wf_inv",
                    tasks={"t1": t_base},
                    timeout_seconds=inv,  # type: ignore
                )

    def test_timeout_hierarchy_and_boundary_conditions(self):
        """Validates the 3-level timeout hierarchy boundaries across contracts."""
        t_base = TaskDefinition(task_id="t1", capability=Capability.BASELINE_EVALUATION, handler="h")

        # Level 1: ExecutionContext (0.0, 300.0]
        ctx_min = ExecutionContext(trace_id="c1", timeout_seconds=0.001)
        self.assertAlmostEqual(ctx_min.timeout_seconds, 0.001)
        ctx_max = ExecutionContext(trace_id="c2", timeout_seconds=300.0)
        self.assertEqual(ctx_max.timeout_seconds, 300.0)

        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="c3", timeout_seconds=0.0)
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="c4", timeout_seconds=-0.001)
        with self.assertRaises(ContractViolationError):
            ExecutionContext(trace_id="c5", timeout_seconds=300.001)

        # Level 2: WorkflowDefinition (default 30.0s, cap 60.0s)
        wf_default = WorkflowDefinition(workflow_id="wf_def", tasks={"t1": t_base})
        self.assertEqual(wf_default.timeout_seconds, 30.0)

        wf_60 = WorkflowDefinition(workflow_id="wf_60", tasks={"t1": t_base}, timeout_seconds=60.0)
        self.assertEqual(wf_60.timeout_seconds, 60.0)

        wf_clamped = WorkflowDefinition(workflow_id="wf_clamp", tasks={"t1": t_base}, timeout_seconds=120.0)
        self.assertEqual(wf_clamped.timeout_seconds, 60.0)

        with self.assertRaises(ContractViolationError):
            WorkflowDefinition(workflow_id="wf_z", tasks={"t1": t_base}, timeout_seconds=0.0)
        with self.assertRaises(ContractViolationError):
            WorkflowDefinition(workflow_id="wf_n", tasks={"t1": t_base}, timeout_seconds=-1.0)

        # Level 3: TaskDefinition (default 5.0s, cap 15.0s)
        td_default = TaskDefinition(task_id="td_def", capability=Capability.BASELINE_EVALUATION, handler="h")
        self.assertEqual(td_default.timeout_seconds, 5.0)

        td_15 = TaskDefinition(task_id="td_15", capability=Capability.BASELINE_EVALUATION, handler="h", timeout_seconds=15.0)
        self.assertEqual(td_15.timeout_seconds, 15.0)

        td_clamped = TaskDefinition(task_id="td_clamp", capability=Capability.BASELINE_EVALUATION, handler="h", timeout_seconds=45.0)
        self.assertEqual(td_clamped.timeout_seconds, 15.0)

        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="td_z", capability=Capability.BASELINE_EVALUATION, handler="h", timeout_seconds=0.0)
        with self.assertRaises(ContractViolationError):
            TaskDefinition(task_id="td_n", capability=Capability.BASELINE_EVALUATION, handler="h", timeout_seconds=-5.0)

    def test_task_output_invariants(self):
        """TaskOutput confidence and provenance validation."""
        out = TaskOutput(
            data={"score": 85},
            provenance=ProvenanceType.PREDICTED,
            confidence=0.95,
            warnings=["warning_1"],
        )
        self.assertEqual(out.data["score"], 85)
        self.assertEqual(out.provenance, ProvenanceType.PREDICTED)
        self.assertEqual(out.confidence, 0.95)
        self.assertEqual(out.warnings, ("warning_1",))

        # Invalid provenance
        with self.assertRaises(ContractViolationError):
            TaskOutput(data={}, provenance="invalid")  # type: ignore

        # Invalid confidence
        with self.assertRaises(ContractViolationError):
            TaskOutput(data={}, provenance=ProvenanceType.PREDICTED, confidence=-0.1)
        with self.assertRaises(ContractViolationError):
            TaskOutput(data={}, provenance=ProvenanceType.PREDICTED, confidence=1.5)
        with self.assertRaises(ContractViolationError):
            TaskOutput(data={}, provenance=ProvenanceType.PREDICTED, confidence=float("nan"))

        # Serialization
        out_dict = out.to_dict()
        self.assertEqual(out_dict["data"], {"score": 85})
        self.assertEqual(out_dict["provenance"], "predicted")
        self.assertEqual(out_dict["confidence"], 0.95)
        self.assertEqual(out_dict["warnings"], ["warning_1"])

    def test_task_result_and_execution_result_invariants(self):
        """TaskResult and ExecutionResult nesting, token generation, and serialization."""
        out = TaskOutput(
            data={"result": "ok"},
            provenance=ProvenanceType.OBSERVED,
        )
        tr = TaskResult(
            task_id="t1",
            capability=Capability.BASELINE_EVALUATION,
            status=StepStatus.COMPLETED,
            output=out,
            latency_ms=120.5,
            retry_count=1,
        )
        self.assertEqual(tr.task_id, "t1")
        self.assertEqual(tr.status, StepStatus.COMPLETED)
        self.assertIsNotNone(tr.execution_token)
        self.assertEqual(tr.latency_ms, 120.5)

        # TaskResult rejects non-TaskOutput output
        with self.assertRaises(ContractViolationError):
            TaskResult(
                task_id="t1",
                capability=Capability.BASELINE_EVALUATION,
                status=StepStatus.COMPLETED,
                output={"not": "TaskOutput"},  # type: ignore
            )

        # ExecutionResult nesting
        er = ExecutionResult(
            trace_id="tr_100",
            workflow_id="wf_test",
            status=WorkflowStatus.COMPLETED,
            task_results={"t1": tr},
            total_latency_ms=150.0,
            errors=["err_1"],
        )
        self.assertEqual(er.trace_id, "tr_100")
        self.assertEqual(er.status, WorkflowStatus.COMPLETED)
        self.assertEqual(len(er.task_results), 1)
        self.assertEqual(er.errors, ("err_1",))

        # Rejection: task_results key does NOT match TaskResult.task_id
        with self.assertRaises(ContractViolationError) as cm:
            ExecutionResult(
                trace_id="tr_100",
                workflow_id="wf_test",
                status=WorkflowStatus.COMPLETED,
                task_results={"mismatched_key": tr},
                total_latency_ms=10.0,
            )
        self.assertIn("does not match TaskResult.task_id", str(cm.exception))

        # ExecutionResult rejects non-TaskResult in task_results
        with self.assertRaises(ContractViolationError):
            ExecutionResult(
                trace_id="tr_100",
                workflow_id="wf_test",
                status=WorkflowStatus.COMPLETED,
                task_results={"t1": "bad_result"},  # type: ignore
                total_latency_ms=10.0,
            )

        # Full recursive serialization of ExecutionResult
        er_dict = er.to_dict()
        self.assertEqual(er_dict["trace_id"], "tr_100")
        self.assertEqual(er_dict["status"], "completed")
        self.assertIn("t1", er_dict["task_results"])
        self.assertEqual(er_dict["task_results"]["t1"]["status"], "completed")
        self.assertEqual(er_dict["task_results"]["t1"]["output"]["data"], {"result": "ok"})
        self.assertEqual(er_dict["task_results"]["t1"]["output"]["provenance"], "observed")
        self.assertEqual(er_dict["errors"], ["err_1"])

    def test_json_serializability_across_all_contracts(self):
        """All 7 approved contracts must serialize to native valid JSON via json.dumps(to_dict())."""
        ctx = ExecutionContext(trace_id="tr1", user_id="u1", session_id="s1", timeout_seconds=10.0, metadata={"k": "v"})
        t_in = TaskInput(capability=Capability.DOCUMENT_PARSING, payload={"text": "sample resume", "flag": True, "count": 5}, context=ctx)
        t_out = TaskOutput(data={"parsed": {"name": "John"}}, provenance=ProvenanceType.OBSERVED, confidence=0.99, warnings=["w1"])
        t_def = TaskDefinition(task_id="t1", capability=Capability.DOCUMENT_PARSING, handler="doc.parse", depends_on=["dep1"], timeout_seconds=5.0)
        wf_def = WorkflowDefinition(workflow_id="wf1", tasks={"t1": t_def}, timeout_seconds=15.0)
        t_res = TaskResult(task_id="t1", capability=Capability.DOCUMENT_PARSING, status=StepStatus.COMPLETED, output=t_out, latency_ms=12.5)
        exec_res = ExecutionResult(trace_id="tr1", workflow_id="wf1", status=WorkflowStatus.COMPLETED, task_results={"t1": t_res}, total_latency_ms=15.0, errors=["e1"])

        all_contracts = [ctx, t_in, t_out, t_def, wf_def, t_res, exec_res]
        for c in all_contracts:
            d = c.to_dict()
            json_str = json.dumps(d)
            self.assertIsInstance(json_str, str)
            self.assertGreater(len(json_str), 10)
            # Round-trip check
            loaded = json.loads(json_str)
            self.assertIsInstance(loaded, dict)

    # ─────────────────────────────────────────────────────────────
    # 7. Domain Exception Hierarchy
    # ─────────────────────────────────────────────────────────────

    def test_domain_exception_hierarchy(self):
        """All domain exceptions must inherit from PIEException."""
        self.assertTrue(issubclass(ContractViolationError, PIEException))
        self.assertTrue(issubclass(PolicyViolationError, PIEException))
        self.assertTrue(issubclass(UnauthorizedCapabilityError, PIEException))
        self.assertTrue(issubclass(WorkflowCycleError, PIEException))
        self.assertTrue(issubclass(TaskTimeoutError, PIEException))
        self.assertTrue(issubclass(RegistryModuleNotFoundError, PIEException))
        self.assertTrue(issubclass(RegistryModelNotFoundError, PIEException))


if __name__ == "__main__":
    unittest.main()
