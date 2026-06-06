"""Product State Machine — unified lifecycle tracking per product.

Provides machine-readable state transitions, stop reasons, and
next-action inference for the autonomous content pipeline.

Public API:
    Phase           — enum of lifecycle phases
    StopReason      — enum of machine-readable stop reasons
    ProductState    — state record with transition validation
    infer_phase     — determine current phase from existing artifacts
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


PRODUCT_STATE_SCHEMA_VERSION = "1.0.0"


class Phase(str, Enum):
    """Lifecycle phases for a product."""
    DISCOVERED = "discovered"
    SOURCE_CHANGED = "source_changed"
    SNAPSHOT_CAPTURED = "snapshot_captured"
    FACTS_EXTRACTED = "facts_extracted"
    FACTS_VERIFIED = "facts_verified"
    PLAN_COMPILED = "plan_compiled"
    CONTENT_GENERATED = "content_generated"
    CLAIMS_VERIFIED = "claims_verified"
    QUALITY_EVALUATED = "quality_evaluated"
    REGRESSION_PASSED = "regression_passed"
    READY_FOR_REVIEW = "ready_for_review"
    BLOCKED_EXTERNAL = "blocked_external"
    RETRYABLE_FAILURE = "retryable_failure"
    QUARANTINED = "quarantined"


class StopReason(str, Enum):
    """Machine-readable stop reasons."""
    CONTINUE = "continue_autonomously"
    BLOCKED_EXTERNAL_APPROVAL = "blocked_external_approval"
    BLOCKED_CREDENTIALS = "blocked_credentials"
    BLOCKED_UNSAFE_WORKTREE = "blocked_unsafe_worktree"
    BLOCKED_LICENSE_RISK = "blocked_license_risk"
    BLOCKED_TOOL_UNAVAILABLE = "blocked_tool_unavailable"
    BLOCKED_VALIDATOR_CONTRADICTION = "blocked_validator_contradiction"
    QUARANTINED_UNSUPPORTED_CLAIMS = "quarantined_unsupported_claims"
    QUARANTINED_REPEATED_FAILURE = "quarantined_repeated_failure"
    READY_FOR_PUBLISH_APPROVAL = "ready_for_publish_approval"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    RETRYABLE_FAILURE = "retryable_failure"


# Allowed transitions: from_phase -> set of valid to_phases
ALLOWED_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.DISCOVERED: {Phase.SOURCE_CHANGED, Phase.SNAPSHOT_CAPTURED},
    Phase.SOURCE_CHANGED: {Phase.SNAPSHOT_CAPTURED, Phase.RETRYABLE_FAILURE},
    Phase.SNAPSHOT_CAPTURED: {Phase.FACTS_EXTRACTED, Phase.RETRYABLE_FAILURE},
    Phase.FACTS_EXTRACTED: {Phase.FACTS_VERIFIED, Phase.RETRYABLE_FAILURE},
    Phase.FACTS_VERIFIED: {Phase.PLAN_COMPILED, Phase.RETRYABLE_FAILURE},
    Phase.PLAN_COMPILED: {Phase.CONTENT_GENERATED, Phase.RETRYABLE_FAILURE},
    Phase.CONTENT_GENERATED: {Phase.CLAIMS_VERIFIED, Phase.RETRYABLE_FAILURE},
    Phase.CLAIMS_VERIFIED: {Phase.QUALITY_EVALUATED, Phase.RETRYABLE_FAILURE},
    Phase.QUALITY_EVALUATED: {Phase.REGRESSION_PASSED, Phase.RETRYABLE_FAILURE},
    Phase.REGRESSION_PASSED: {Phase.READY_FOR_REVIEW},
    Phase.READY_FOR_REVIEW: {Phase.BLOCKED_EXTERNAL, Phase.DISCOVERED},
    Phase.BLOCKED_EXTERNAL: {Phase.READY_FOR_REVIEW, Phase.DISCOVERED},
    Phase.RETRYABLE_FAILURE: {
        Phase.SNAPSHOT_CAPTURED, Phase.FACTS_EXTRACTED, Phase.FACTS_VERIFIED,
        Phase.PLAN_COMPILED, Phase.CONTENT_GENERATED, Phase.CLAIMS_VERIFIED,
        Phase.QUALITY_EVALUATED, Phase.QUARANTINED,
    },
    Phase.QUARANTINED: {Phase.DISCOVERED},  # Only manual reset
}

MAX_RETRIES = 3


class IllegalTransitionError(Exception):
    """Raised when a state transition is not allowed."""


@dataclass
class ProductState:
    """State record for a single product (family/platform)."""
    schema_version: str = PRODUCT_STATE_SCHEMA_VERSION
    family: str = ""
    platform: str = ""
    phase: str = Phase.DISCOVERED.value
    stop_reason: str = StopReason.CONTINUE.value
    retry_count: int = 0
    last_transition: str = ""
    transition_history: list[dict[str, str]] = field(default_factory=list)

    def transition(self, to_phase: Phase, reason: str = "") -> None:
        """Validate and execute a state transition.

        Raises IllegalTransitionError if the transition is not allowed.
        Auto-quarantines after MAX_RETRIES retryable failures.
        """
        from_phase = Phase(self.phase)
        allowed = ALLOWED_TRANSITIONS.get(from_phase, set())

        if to_phase not in allowed:
            raise IllegalTransitionError(
                f"Transition {from_phase.value} -> {to_phase.value} not allowed. "
                f"Allowed: {sorted(p.value for p in allowed)}"
            )

        # Track retries
        if to_phase == Phase.RETRYABLE_FAILURE:
            self.retry_count += 1
            self.stop_reason = StopReason.RETRYABLE_FAILURE.value
            if self.retry_count >= MAX_RETRIES:
                # Auto-quarantine after max retries
                to_phase = Phase.QUARANTINED
                self.stop_reason = StopReason.QUARANTINED_REPEATED_FAILURE.value
        elif to_phase == Phase.BLOCKED_EXTERNAL:
            self.stop_reason = StopReason.BLOCKED_EXTERNAL_APPROVAL.value
        elif to_phase == Phase.READY_FOR_REVIEW:
            self.stop_reason = StopReason.READY_FOR_HUMAN_REVIEW.value
        else:
            self.stop_reason = StopReason.CONTINUE.value
            if from_phase == Phase.RETRYABLE_FAILURE:
                # Successful recovery resets retry count
                self.retry_count = 0

        now = datetime.now(timezone.utc).isoformat()
        self.transition_history.append({
            "from": from_phase.value,
            "to": to_phase.value,
            "at": now,
            "reason": reason,
        })
        self.phase = to_phase.value
        self.last_transition = now

    def is_terminal(self) -> bool:
        """Check if current phase is a terminal/blocking state."""
        return Phase(self.phase) in {
            Phase.READY_FOR_REVIEW,
            Phase.BLOCKED_EXTERNAL,
            Phase.QUARANTINED,
        }

    def is_actionable(self) -> bool:
        """Check if current phase allows autonomous continuation."""
        return (
            not self.is_terminal()
            and self.stop_reason == StopReason.CONTINUE.value
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> ProductState:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def read(cls, path: Path) -> ProductState:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def infer_phase(family: str, platform: str, knowledge_root: Path | None = None) -> Phase:
    """Infer the current lifecycle phase from existing artifacts.

    Checks for the presence of knowledge artifacts to determine how far
    the pipeline has progressed for this product.
    """
    if knowledge_root is None:
        knowledge_root = Path(__file__).resolve().parents[3] / "knowledge"

    merged = knowledge_root / family / platform / "merged"
    scout = knowledge_root / family / platform / "scout"

    if not (merged.exists() or scout.exists()):
        return Phase.DISCOVERED

    if not (merged / "api_surface.json").exists():
        if (scout / "api_surface.json").exists():
            return Phase.FACTS_EXTRACTED
        return Phase.SNAPSHOT_CAPTURED

    # Merged exists — check for enrichment
    model_path = merged / "model.yaml"
    if model_path.exists():
        import yaml
        model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
        stale = model.get("stale_since")
        if stale:
            return Phase.SOURCE_CHANGED

    # Has merged knowledge — at least FACTS_VERIFIED
    if (merged / "claims.json").exists():
        return Phase.FACTS_VERIFIED

    return Phase.FACTS_EXTRACTED
