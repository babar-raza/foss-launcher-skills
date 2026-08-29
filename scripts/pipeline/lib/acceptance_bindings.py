"""Acceptance-artifact input bindings (R-1, MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH
TC-MT040-49).

Root problem (W9 in reports/sprint/pdf-typescript-hardening/preflight/design.md):
`readiness_scorecard.py`'s readiness.md and S-90's final-verdict.md are both
computed from knowledge/evaluator state at one point in time, but neither file
records WHICH state it was computed against -- so an operator (or another
script) reading an old readiness.md/final-verdict.md has no way to tell
whether it still describes the product's current knowledge, or predates a
knowledge promotion / extraction-logic change that has since made it wrong.

Observed live: cells/typescript's own readiness.md (2026-06-15, verdict NOT
READY) and its S-90 final-verdict.md (2026-06-06, verdict PUBLISH) directly
contradict each other, and BOTH predate the product's 2026-08-28 knowledge
re-sync -- there was no mechanical way to know either one was stale until a
human noticed the dates by hand.

This module computes one small, stable "bindings" dict -- the current inputs
an acceptance artifact for a given family/platform is judged against -- for
any caller that writes or reads such an artifact. Two structural layers of
this repo's own hardening (D-1 platform_capabilities.yaml, D-4 module
assignment, D-2 fidelity gate) had not landed yet when this module was
written, so their fields are forward-declared as ``None`` here and will be
populated by later taskcards without changing this module's shape -- callers
must always read the dict by key, never assume every key is non-None.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def _read_model_yaml(family: str, platform: str) -> dict:
    path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "model.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, Exception):  # noqa: BLE001 -- best-effort, never crash a caller
        return {}


def _evaluator_logic_version() -> "str | None":
    try:
        import sys
        pipeline_root = str(Path(__file__).resolve().parents[1])
        if pipeline_root not in sys.path:
            sys.path.insert(0, pipeline_root)
        from content_eval import EVALUATOR_FREEZE_VERSION
        return EVALUATOR_FREEZE_VERSION
    except Exception:  # noqa: BLE001 -- best-effort, never crash a caller
        return None


def compute_bindings(family: str, platform: str) -> dict:
    """Return the current input-state dict an acceptance artifact for
    *family*/*platform* should be judged against.

    Every field is either a real current value or ``None`` (never a stale
    cached guess) -- ``None`` means "unknown/not applicable right now," and
    callers comparing a stored bindings dict against a fresh
    ``compute_bindings()`` call must treat a ``None``-vs-``None`` pair as
    "cannot determine, do not flag," not as a mismatch.
    """
    model = _read_model_yaml(family, platform)
    return {
        "model_sha": model.get("repo_sha"),
        "extractor_hash": model.get("extractor_hash"),
        "evaluator_logic_version": _evaluator_logic_version(),
        # Forward-declared: populated once their owning taskcards land.
        # D-4 (TC-MT040-43) writes MODULE_ASSIGNMENT_VERSION into model.yaml.
        "module_assignment_version": model.get("module_assignment_version"),
        # D-4/G-TS-01 (TC-MT040-18) bumps this in lib/reference_filter.py;
        # read it directly from there once it exists as a real product-level
        # signal (today it is a fixed module constant, not yet per-product).
        "grouped_index_generator_version": None,
        # D-1 (TC-MT040-40) adds config/platform_capabilities.yaml.
        "platform_capabilities_digest": _file_digest(
            _REPO_ROOT / "scripts" / "pipeline" / "config" / "platform_capabilities.yaml"
        ),
    }


def _file_digest(path: Path) -> "str | None":
    if not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def bindings_status(stored: "dict | None", current: dict) -> str:
    """Compare a stored bindings dict (read from an artifact) against the
    current bindings for the same product.

    Returns one of:
      "unverifiable" -- *stored* is None or has no model_sha at all (a
                         legacy artifact predating this module, or a fresh
                         artifact with no knowledge yet) -- never silently
                         treated as current.
      "current"       -- the fields both sides agree are known (non-None on
                          both) all match.
      "stale"         -- at least one field both sides know differs.
    """
    if not stored or not stored.get("model_sha"):
        return "unverifiable"
    for key in ("model_sha", "extractor_hash", "evaluator_logic_version"):
        stored_val = stored.get(key)
        current_val = current.get(key)
        if stored_val is not None and current_val is not None and stored_val != current_val:
            return "stale"
    return "current"


def format_bindings_yaml(bindings: dict, *, indent: str = "") -> str:
    """Render a bindings dict as a small YAML-ish block for embedding in a
    markdown artifact (readiness.md / an H-gate sample file), matching the
    plain ``key: "value"`` style ``human_review_sampler.py``'s own
    ``_signoff_block()`` already uses -- no external YAML dependency needed
    for round-tripping, since ``parse_bindings_yaml`` below reads the same
    simple shape back with a line-anchored regex, not a real YAML parser.
    """
    lines = [f"{indent}bindings:"]
    for key, value in bindings.items():
        rendered = "null" if value is None else json.dumps(value)
        lines.append(f"{indent}  {key}: {rendered}")
    return "\n".join(lines)


def parse_bindings_yaml(text: str) -> "dict | None":
    """Extract a ``bindings:`` block written by ``format_bindings_yaml``
    back out of an artifact's text. Returns ``None`` if no such block is
    present (a legacy artifact) -- never raises on malformed input.
    """
    import re
    m = re.search(r"^bindings:\s*\n((?:^  [\w_]+:.*\n?)+)", text, re.MULTILINE)
    if not m:
        return None
    result: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, raw_value = line.partition(":")
        key = key.strip()
        raw_value = raw_value.strip()
        try:
            result[key] = json.loads(raw_value)
        except ValueError:
            result[key] = raw_value.strip('"')
    return result
