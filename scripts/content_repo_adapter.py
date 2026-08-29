"""External content repository adapter.

Centralizes path and mode decisions for standalone skills that operate against
an external content repository. The adapter is deliberately conservative: it
fails closed on missing content roots and forbids writes to the live aspose.org
content tree unless a caller only resolves paths for read-only inspection.

2026-08-29 sync note: the original write-safety boundary was a single
hardcoded ASPOSE_CONTENT_ROOT constant used directly inside
assert_write_allowed -- this was the exact class of structural coupling
scripts/ci/checks/check_hardcoded_external_coupling.py was built to catch
(found live during that sync; present, undetected, through two prior
"parity complete" closures). ASPOSE_CONTENT_ROOT is preserved below,
unchanged, as the documented backward-compatible DEFAULT boundary --
existing tests construct write targets under it directly and continue to
pass unchanged -- but assert_write_allowed now resolves the boundary via
resolve_forbidden_write_root() first, which is config/env driven, so a
caller pointed at a different content repo is no longer silently coupled
to this one hardcoded path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from config_loader import ConfigError


ASPOSE_CONTENT_ROOT = Path("D:/onedrive/Documents/GitHub/aspose.org/content").resolve()
OBSOLETE_CLONE_CACHE_MARKER = "foss-launcher/runs/.clone_cache"
FORBIDDEN_CONTENT_ROOT_ENV = "FORBIDDEN_CONTENT_ROOT"


@dataclass(frozen=True)
class AdapterContext:
    """Resolved path and execution context for a standalone skill."""

    content_root: Path
    output_root: Path
    clone_cache: Path
    metrics_mode: str
    dry_run: bool


def _as_path(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser().resolve()


def _config_get(config: Mapping[str, object] | None, *keys: str) -> str | None:
    if not config:
        return None
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def resolve_content_root(
    config: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    *,
    must_exist: bool = True,
) -> Path:
    """Resolve the external content repository root.

    Resolution order:
    1. ``CONTENT_REPO_PATH``
    2. ``config["content_root"]``
    3. ``config["content_repo"]`` for backward compatibility
    """

    env = os.environ if env is None else env
    raw = env.get("CONTENT_REPO_PATH") or _config_get(config, "content_root", "content_repo")
    if not raw:
        raise ConfigError("Content root not configured. Set CONTENT_REPO_PATH or config content_root/content_repo.")
    path = _as_path(raw)
    if must_exist and not path.is_dir():
        raise ConfigError(f"Content root does not exist or is not a directory: {path}")
    return path


def resolve_output_root(
    output_root: str | os.PathLike[str] | None = None,
    config: Mapping[str, object] | None = None,
    *,
    default: str | os.PathLike[str] = "reports",
) -> Path:
    """Resolve where generated reports, manifests, and shadow outputs go."""

    raw = output_root or _config_get(config, "output_root") or default
    return _as_path(raw)


def resolve_clone_cache(
    config: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    *,
    default: str | os.PathLike[str] = "runs/.clone_cache",
) -> Path:
    """Resolve clone cache and reject obsolete foss-launcher cache references."""

    env = os.environ if env is None else env
    raw = env.get("ASPOSE_CLONE_CACHE") or _config_get(config, "clone_cache", "clone_cache_root") or str(default)
    normalized = str(raw).replace("\\", "/")
    if OBSOLETE_CLONE_CACHE_MARKER in normalized:
        raise ConfigError(f"Refusing obsolete clone-cache path: {raw}")
    return _as_path(raw)


def metrics_mode(
    env: Mapping[str, str] | None = None,
    *,
    submit: bool = False,
) -> str:
    """Return metrics mode: ``dry-run``, ``submit``, or ``disabled``.

    Production submission requires explicit ``submit=True`` and both endpoint
    and token. Missing credentials never block local dry-runs.
    """

    env = os.environ if env is None else env
    if not submit:
        return "dry-run"
    if env.get("AGENT_METRICS_ENDPOINT") and env.get("AGENT_METRICS_TOKEN"):
        return "submit"
    return "disabled"


def resolve_forbidden_write_root(
    config: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the write-safety boundary a caller must not write into directly.

    Resolution order:
    1. ``FORBIDDEN_CONTENT_ROOT`` env var
    2. ``config["forbidden_content_root"]``
    3. ``ASPOSE_CONTENT_ROOT`` -- this repo's original hardcoded default,
       preserved for backward compatibility. Existing callers that rely on
       the default boundary (including tests that construct targets under
       ASPOSE_CONTENT_ROOT directly) continue to work unchanged.
    """

    env = os.environ if env is None else env
    raw = env.get(FORBIDDEN_CONTENT_ROOT_ENV) or _config_get(config, "forbidden_content_root")
    if raw:
        return _as_path(raw)
    return ASPOSE_CONTENT_ROOT


def assert_write_allowed(
    target: str | os.PathLike[str],
    *,
    dry_run: bool = False,
    allow_live_aspose_content: bool = False,
    forbidden_root: Path | None = None,
    config: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Validate a write target and return its resolved path.

    Dry-runs are allowed to compute forbidden targets for reporting. Real
    writes under the forbidden boundary (see resolve_forbidden_write_root)
    are denied by default.
    """

    path = _as_path(target)
    if dry_run:
        return path
    boundary = forbidden_root if forbidden_root is not None else resolve_forbidden_write_root(config, env)
    try:
        path.relative_to(boundary)
    except ValueError:
        return path
    if allow_live_aspose_content:
        return path
    raise ConfigError(f"Refusing write under forbidden content root: {path}")


def build_context(
    config: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    *,
    output_root: str | os.PathLike[str] | None = None,
    dry_run: bool = True,
    submit_metrics: bool = False,
    content_must_exist: bool = True,
) -> AdapterContext:
    """Resolve all common adapter settings in one call."""

    return AdapterContext(
        content_root=resolve_content_root(config, env, must_exist=content_must_exist),
        output_root=resolve_output_root(output_root, config),
        clone_cache=resolve_clone_cache(config, env),
        metrics_mode=metrics_mode(env, submit=submit_metrics),
        dry_run=dry_run,
    )
