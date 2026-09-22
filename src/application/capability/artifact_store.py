"""Per-run in-memory object storage for Capability Artifact Flow Demo V1."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.domain import GoalRef, MissingInformation


class ArtifactFlowError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        missing_information: tuple[MissingInformation, ...] = (),
    ) -> None:
        self.code = code
        self.message = message
        self.missing_information = missing_information
        super().__init__(message)


def _component(value: object, *, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or ":" in value
    ):
        raise ArtifactFlowError(
            "ARTIFACT_CONTEXT_INVALID", f"Artifact {name} is invalid."
        )
    return value


def split_artifact_ref(ref: object) -> tuple[str, str]:
    if not isinstance(ref, str) or ref.count(":") != 1:
        raise ArtifactFlowError(
            "ARTIFACT_CONTEXT_INVALID", "Artifact reference is invalid."
        )
    artifact_type, artifact_id = ref.split(":", 1)
    return (
        _component(artifact_type, name="type"),
        _component(artifact_id, name="id"),
    )


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    artifact_type: str
    artifact_id: str
    value: dict[str, Any]

    @property
    def ref(self) -> str:
        return f"{self.artifact_type}:{self.artifact_id}"


class ArtifactStore:
    """A single-run store that deep-copies JSON-compatible business objects."""

    def __init__(self) -> None:
        self._items: dict[str, StoredArtifact] = {}
        self._bound_goal_ref: GoalRef | None = None

    def bind_goal(self, goal_ref: GoalRef) -> None:
        if self._bound_goal_ref is None:
            self._bound_goal_ref = goal_ref
            return
        if self._bound_goal_ref != goal_ref:
            raise ArtifactFlowError(
                "ARTIFACT_GOAL_CHANGED",
                "Artifact Store cannot be used with a different Goal.",
            )
        raise ArtifactFlowError(
            "ARTIFACT_STORE_REUSED",
            "Artifact Store is already bound to a completed or active run.",
        )

    def put(
        self,
        artifact_type: str,
        artifact_id: str,
        value: dict[str, Any],
    ) -> str:
        artifact_type = _component(artifact_type, name="type")
        artifact_id = _component(artifact_id, name="id")
        if not isinstance(value, dict):
            raise ArtifactFlowError(
                "ARTIFACT_CONTEXT_INVALID", "Artifact value must be an object."
            )
        try:
            json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ArtifactFlowError(
                "ARTIFACT_CONTEXT_INVALID",
                "Artifact value must be JSON compatible.",
            ) from exc
        ref = f"{artifact_type}:{artifact_id}"
        if ref in self._items:
            raise ArtifactFlowError(
                "ARTIFACT_DUPLICATE", "Artifact reference already exists."
            )
        self._items[ref] = StoredArtifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            value=deepcopy(value),
        )
        return ref

    def get(self, ref: str) -> StoredArtifact:
        split_artifact_ref(ref)
        artifact = self._items.get(ref)
        if artifact is None:
            raise ArtifactFlowError(
                "ARTIFACT_NOT_FOUND", "Referenced artifact does not exist."
            )
        return StoredArtifact(
            artifact_type=artifact.artifact_type,
            artifact_id=artifact.artifact_id,
            value=deepcopy(artifact.value),
        )

    def contains(self, ref: str) -> bool:
        split_artifact_ref(ref)
        return ref in self._items
