"""
lib/example_verification/policy.py

CONTRACT: scripts/pipeline/lib/example_verification/policy.py
  purpose: Policy (how much verification a caller is asking for -- max
           tier, whether acquiring a real environment is allowed, timeouts,
           budgets, chain execution mode, the process-environment allow-
           list) and ProductContext (which product/package this run is
           verifying, derived from the same inputs S-120 already threads
           through its call chain: a factpack dict, or a product's merged
           knowledge). No consumer calls this yet (rollout step C2 ships it
           as tested, unwired library code); C3 wires the first real caller
           when it extracts S-120's runners behind this package's API.
  inputs:  explicit kwargs, a factpack dict, or a family/platform pair
  outputs: Policy, ProductContext
  owner_domain: content-quality
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
_KNOWLEDGE_BASE = _REPO_ROOT / "knowledge"
_DEFAULT_CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"


def clone_cache_path(family: str, platform: str, root: "Path | None" = None) -> Path:
    """Same layout S-120 already uses (`_product_clone_cache`,
    readme_refresh_run.py:368-369): `{root}/aspose_{family}_{platform}`,
    defaulting to this repo's real clone-cache root (`runs/.clone_cache`,
    itself a `configure()`-seam global in readme_refresh_run.py)."""
    base = root if root is not None else _DEFAULT_CLONE_CACHE_ROOT
    return base / f"aspose_{family}_{platform}"

# Per-platform default timeouts (Round 3 G) -- overridable per call, and
# later per-product via a factpack's own `verification.timeouts` (Phase 2
# item G, not built here). Seconds.
_DEFAULT_TIMEOUTS: dict[str, float] = {
    "python": 60.0,
    "typescript": 120.0,
    "go": 60.0,
    "net": 120.0,
    "java": 180.0,
    "rust": 60.0,
    "cpp": 180.0,
}

# The exec_env allow-list (Round 3 H): never the repo's own PYTHONPATH, so
# an executed block can't accidentally import this pipeline's own modules.
DEFAULT_ENV_ALLOWLIST: frozenset[str] = frozenset({
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "HOME", "USERPROFILE",
    "COMSPEC", "PATHEXT", "APPDATA", "LOCALAPPDATA",
})


@dataclass(frozen=True, slots=True)
class Timeouts:
    """Elapsed-time budgets for one block/chain execution (Round 3 G).
    A TIMEOUT is retried once at `retry_multiplier` the original budget;
    if the retry then passes, the result is reported SLOW (advisory) with
    both timings recorded -- a hang still ends as TIMEOUT after the retry."""

    seconds: float
    retry_multiplier: float = 2.0

    @classmethod
    def for_platform(cls, platform: str) -> "Timeouts":
        return cls(seconds=_DEFAULT_TIMEOUTS.get(platform, 60.0))


@dataclass(frozen=True, slots=True)
class Policy:
    """How much verification a caller is asking for."""

    max_tier: int = 2
    allow_acquire: bool = False
    timeouts: Timeouts = field(default_factory=lambda: Timeouts(seconds=60.0))
    budget_seconds: float | None = None
    chain_mode: str = "single"          # "single" (Round 3 F) | "replay" (transitional)
    env_allowlist: frozenset[str] = DEFAULT_ENV_ALLOWLIST

    def __post_init__(self) -> None:
        if self.chain_mode not in ("single", "replay"):
            raise ValueError(f"Policy: invalid chain_mode {self.chain_mode!r}")
        if self.max_tier < 0 or self.max_tier > 4:
            raise ValueError(f"Policy: max_tier out of range: {self.max_tier!r}")

    @classmethod
    def for_platform(cls, platform: str, *, max_tier: int | None = None,
                      allow_acquire: bool = False) -> "Policy":
        """A reasonable default policy for one platform: registry.py's
        offline_tier when acquire isn't allowed, else its max_tier, unless
        the caller pins an explicit max_tier."""
        from . import registry
        contract = registry.PLATFORM_CONTRACT.get(platform)
        if max_tier is not None:
            tier = max_tier
        elif contract is None:
            tier = 1
        else:
            tier = contract.max_tier if allow_acquire else min(contract.offline_tier, contract.max_tier)
        return cls(
            max_tier=tier, allow_acquire=allow_acquire,
            timeouts=Timeouts.for_platform(platform),
        )


@dataclass(frozen=True, slots=True)
class ProductContext:
    """Which product/package this verification run concerns."""

    family: str = ""
    platform: str = ""
    published: bool = False
    package_name: str = ""
    manifest_version: str | None = None
    clone_head: str | None = None

    @classmethod
    def from_factpack(cls, factpack: dict[str, Any], *, family: str = "", platform: str = "") -> "ProductContext":
        """Build from the factpack dict shape S-120 already threads through
        its acquire functions: `{"published": bool, "candidate": {"name":
        str, "version": str}}`."""
        candidate = factpack.get("candidate") or {}
        return cls(
            family=family,
            platform=platform,
            published=bool(factpack.get("published", False)),
            package_name=str(candidate.get("name", "")),
            manifest_version=candidate.get("version"),
        )

    @classmethod
    def from_knowledge(cls, family: str, platform: str) -> "ProductContext":
        """Build from a product's merged knowledge on disk. Minimal by
        design: only `model.yaml`'s existence and its `repo_sha`/`canonical_import`
        fields are read here; a future caller that needs more (e.g. the
        probed live package version from `publication_probe.py`) composes
        that separately rather than this constructor reaching into every
        knowledge artifact speculatively."""
        model_path = _KNOWLEDGE_BASE / family / platform / "merged" / "model.yaml"
        clone_head: str | None = None
        if model_path.is_file():
            try:
                import yaml  # type: ignore[import]
                data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
                clone_head = data.get("repo_sha")
            except Exception:
                clone_head = None
        return cls(family=family, platform=platform, clone_head=clone_head)
