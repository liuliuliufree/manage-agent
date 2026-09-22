"""Deterministic artifact selection and publication metadata for Demo V1."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain import CapabilityStatus, MissingInformation, PlanRef, PlanStep

from .artifact_store import (
    ArtifactFlowError,
    ArtifactStore,
    split_artifact_ref,
)


_UNSUPPORTED_BUSINESS_INPUTS = frozenset({"evidence", "rule_result"})


def _type_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or ":" in value
    ):
        raise ValueError("Artifact type names must be non-empty and contain no colon")
    if value in _UNSUPPORTED_BUSINESS_INPUTS:
        raise ValueError(f"Artifact type {value!r} is not a Demo V1 business input")
    return value


@dataclass(frozen=True, slots=True)
class CapabilityIO:
    required_inputs: tuple[str, ...] = ()
    optional_inputs: tuple[str, ...] = ()
    output_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for values in (self.required_inputs, self.optional_inputs, self.output_types):
            if not isinstance(values, tuple):
                raise ValueError("Capability IO declarations must be tuples")
            normalized = tuple(_type_name(value) for value in values)
            if normalized != values or len(set(values)) != len(values):
                raise ValueError("Capability IO types must be unique normalized strings")
        if set(self.required_inputs) & set(self.optional_inputs):
            raise ValueError("Required and optional input types must not overlap")


@dataclass(frozen=True, slots=True)
class PublishedArtifact:
    ref: str
    source_step_id: str
    source_request_id: str
    source_plan_ref: PlanRef

    def __post_init__(self) -> None:
        split_artifact_ref(self.ref)
        if not self.source_step_id or not self.source_request_id:
            raise ValueError("Published artifact source identity is required")


def normalize_initial_refs(
    known_context: object,
    *,
    store: ArtifactStore,
    allowed_types: frozenset[str],
) -> tuple[str, ...]:
    if known_context is None:
        return ()
    if not isinstance(known_context, dict):
        raise ArtifactFlowError(
            "ARTIFACT_CONTEXT_INVALID", "Initial artifact context is invalid."
        )
    refs: list[str] = []
    seen: set[str] = set()
    for key, values in known_context.items():
        if (
            not isinstance(key, str)
            or not key.endswith("_refs")
            or not key.removesuffix("_refs")
        ):
            raise ArtifactFlowError(
                "ARTIFACT_CONTEXT_INVALID", "Initial artifact context key is invalid."
            )
        artifact_type = key.removesuffix("_refs")
        if artifact_type not in allowed_types or artifact_type in _UNSUPPORTED_BUSINESS_INPUTS:
            raise ArtifactFlowError(
                "ARTIFACT_CONTEXT_INVALID",
                "Initial artifact type is not declared by an executable capability.",
            )
        if not isinstance(values, (list, tuple)) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise ArtifactFlowError(
                "ARTIFACT_CONTEXT_INVALID", "Initial artifact references are invalid."
            )
        for artifact_id in values:
            if artifact_id != artifact_id.strip() or ":" in artifact_id:
                raise ArtifactFlowError(
                    "ARTIFACT_CONTEXT_INVALID", "Initial artifact id is invalid."
                )
            ref = f"{artifact_type}:{artifact_id}"
            artifact = store.get(ref)
            if artifact.artifact_type != artifact_type:
                raise ArtifactFlowError(
                    "ARTIFACT_TYPE_MISMATCH", "Initial artifact type does not match."
                )
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return tuple(refs)


def _missing_input(artifact_type: str, *, ambiguous: bool) -> ArtifactFlowError:
    if ambiguous:
        code = "INPUT_AMBIGUOUS"
        reason = f"存在多个 {artifact_type} 输入，无法确定使用对象"
    else:
        code = "INPUT_REQUIRED"
        reason = f"缺少必需的 {artifact_type} 输入"
    missing = MissingInformation(
        field=f"input_refs.{artifact_type}",
        reason=reason,
        impact="阻止当前能力执行",
        required_before_execution=True,
    )
    return ArtifactFlowError(code, reason, (missing,))


def resolve_input_refs(
    step: PlanStep,
    context: "ExecutionContext",
    io: CapabilityIO,
) -> tuple[str, ...]:
    from .execution_context import ExecutionContext

    if not isinstance(context, ExecutionContext):
        raise ArtifactFlowError("ARTIFACT_CONTEXT_INVALID", "Execution context is invalid.")
    current_step_ids = {item.step_id for item in context.current_plan.steps}
    resolved: list[str] = []
    for artifact_type in (*io.required_inputs, *io.optional_inputs):
        candidates: list[str] = []
        for published in context.published_artifacts.values():
            published_type, _ = split_artifact_ref(published.ref)
            if (
                published_type == artifact_type
                and published.source_step_id in step.depends_on
                and published.source_step_id in current_step_ids
            ):
                source_result = context.step_results.get(published.source_step_id)
                if source_result is not None and source_result.status is CapabilityStatus.SUCCESS:
                    candidates.append(published.ref)
        candidates = list(dict.fromkeys(candidates))
        if not candidates:
            candidates = [
                ref
                for ref in context.initial_refs
                if split_artifact_ref(ref)[0] == artifact_type
            ]
        if len(candidates) > 1:
            raise _missing_input(artifact_type, ambiguous=True)
        if not candidates:
            if artifact_type in io.required_inputs:
                raise _missing_input(artifact_type, ambiguous=False)
            continue
        ref = candidates[0]
        stored = context.artifact_store.get(ref)
        if stored.artifact_type != artifact_type:
            raise ArtifactFlowError(
                "ARTIFACT_TYPE_MISMATCH", "Resolved artifact type does not match."
            )
        resolved.append(ref)
    return tuple(resolved)


__all__ = [
    "ArtifactFlowError",
    "CapabilityIO",
    "PublishedArtifact",
    "normalize_initial_refs",
    "resolve_input_refs",
]
