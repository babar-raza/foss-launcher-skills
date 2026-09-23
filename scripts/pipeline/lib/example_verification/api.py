"""
lib/example_verification/api.py

CONTRACT: scripts/pipeline/lib/example_verification/api.py
  purpose: the ONE public entry point every consumer of this package calls
           (S-63 smoke_test, S-120 readme_refresh_run, S-49 launch_gate,
           S-84 refresh_run, pre-commit, knowledge promotion) --
           MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION/TC-01.
           Pure composition over already-tested modules: no new
           verification logic lives here. Closes RC1, the root cause the
           2026-09-18 audit named for why MT065 closed all 14 of its own
           taskcards while leaving the package unreachable from
           production -- result.py's own docstring already said results
           are "produced by runners/api.py (landing in later rollout
           steps)" and every one of C4/C5/C6/C7's promotion-gate notes
           disclosed that this module was "assigned to no taskcard in the
           current C1-C14 rollout."
  inputs:  a markdown page's file path (or raw text) + family/platform +
           an optional Policy override
  outputs: VerificationReport (result.py) -- the one canonical return
           type. Every consumer converts it further via
           report.to_smoke() / report.to_legacy_s120(), or reads
           report.blocks directly.
  owner_domain: content-quality
  requires_test: true

Two real dispatch paths, both delegating to already-proven code, never
duplicating verification logic:

  - python / typescript: the existing S-120-ported whole-candidate
    functions (runners/python.py::python_verification_runner,
    runners/typescript.py::typescript_verification_runner). These already
    do their own block extraction + chain execution over a WHOLE file;
    verify_page() calls them as-is and adapts their return dict into a
    VerificationReport (_from_whole_candidate_dict below). Deliberately
    NOT retrofitted onto BaseRunner/LanguageRunner in this taskcard --
    runners/base.py's own docstring explicitly reserves that retrofit for
    a later taskcard, to avoid risking regression in proven production
    code in the same step that builds a brand-new, only-synthetically-
    tested abstraction ("build the abstraction from observed duplication,
    not guessed ahead of it").
  - go / dotnet / java / rust / cpp: real LanguageRunner-protocol classes
    (runners/{go,dotnet,java,rust,cpp}.py) driven uniformly through
    BaseRunner, fed blocks from the shared code_fences.py tokenizer.

_LANGUAGE_RUNNER_CLASSES is registry.RUNNER_CLASS_NAMES (TC-02 moved the
platform -> (module, class) mapping there, since registry.py's own
PLATFORM_CONTRACT needs the identical mapping to introspect each runner's
real `ceiling_tier` -- one source, read by both modules, rather than two
copies that could drift the same way registry.py's hand-typed max_tier
values already had by the time this taskcard started).

Known, disclosed limitation (not silently hidden): python/typescript's
whole-candidate functions still use their own private regex for block
extraction (inherited verbatim from S-120), not code_fences.py's shared
tokenizer. MT065 C1 already measured 99.8% agreement between the two
tokenizers portfolio-wide; the 320-file divergence it found was traced to
a real, separate content defect (orphaned closing fences), not a
tokenizer defect. _from_whole_candidate_dict() below does a best-effort
line-number enrichment by position against code_fences.py's own parse of
the same file and silently falls back to (0, 0) if that alignment fails
(e.g. on one of those 320 malformed files) -- it never raises and never
fabricates a wrong line number with false confidence. Unifying the two
tokenizers is follow-on work, not built here, to avoid touching proven
production code in the same commit that builds this seam.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from . import RUNNERS_MODULE_VERSION
from .code_fences import enumerate_code_blocks
from .policy import Policy, ProductContext
from .registry import NON_EXECUTABLE_LANGS, PLATFORM_CONTRACT, RUNNER_CLASS_NAMES
from .result import BlockIdentity, BlockResult, VerificationReport
from .runners.base import BaseRunner, RunOptions

# Sourced from registry.py (TC-02: the one place this mapping lives now,
# so api.py's dispatch table and registry.py's own PLATFORM_CONTRACT
# introspection never drift apart).
_LANGUAGE_RUNNER_CLASSES = RUNNER_CLASS_NAMES

# Platforms whose verification goes through the whole-candidate, S-120-
# ported functions rather than BaseRunner (see module docstring).
WHOLE_CANDIDATE_PLATFORMS: frozenset[str] = frozenset({"python", "typescript"})


def _default_whole_candidate_runners() -> dict:
    from .runners.python import python_verification_runner
    from .runners.typescript import typescript_verification_runner
    return {"python": python_verification_runner, "typescript": typescript_verification_runner}


# --- Test seam (configure() pattern) -- _verify_whole_candidate() looks up
# _cfg_whole_candidate_runners[platform], never a bare late import, so a
# test can swap either function via configure(...) instead of
# monkeypatch.setattr'ing an internal module reference (T2, banned by
# AGENTS.md §16 -- confirmed live by pre-commit Step 18 monkeypatch-lint on
# an earlier version of this module's own test). ---
_cfg_whole_candidate_runners = _default_whole_candidate_runners()


def configure(*, python_runner=None, typescript_runner=None) -> None:
    """Test seam: override the whole-candidate runner functions
    verify_page() dispatches python/typescript to. Call with no args to
    restore the real functions; pass only the one(s) you want to swap."""
    global _cfg_whole_candidate_runners
    defaults = _default_whole_candidate_runners()
    _cfg_whole_candidate_runners = {
        "python": python_runner if python_runner is not None else defaults["python"],
        "typescript": typescript_runner if typescript_runner is not None else defaults["typescript"],
    }


def _load_language_runner(platform: str, family: str = "") -> Any:
    """Every go/dotnet/java/rust/cpp LanguageRunner class requires
    `family` (used to resolve the product's own module/crate/package name
    for import-statement inference, e.g. GoRunner._resolve_go_module_for_family)
    -- an empty string is valid (the runner's own resolver degrades to its
    generic fallback rather than raising) for callers that don't have a
    family yet, e.g. a bare syntax-only tier-1 check.

    Package-relative import, same reasoning as
    registry.py::_introspect_ceiling_tier -- an absolute
    "example_verification.runners.x" string silently fails in any caller
    whose sys.path has scripts/pipeline but not scripts/pipeline/lib."""
    mod_name, class_name = _LANGUAGE_RUNNER_CLASSES[platform]
    mod = importlib.import_module(f".runners.{mod_name}", package=__package__)
    return getattr(mod, class_name)(family)


def verify_page(
    path: "str | Path",
    *,
    family: str = "",
    platform: str,
    policy: "Policy | None" = None,
    factpack: "dict | None" = None,
) -> VerificationReport:
    """Verify one markdown FILE's fenced code blocks for `platform`. Both
    dispatch paths read the real file at `path` (python/typescript's
    whole-candidate functions require a real file on disk; the
    BaseRunner path reads it once here and tokenizes it)."""
    path = Path(path)
    policy = policy or Policy.for_platform(platform)

    if platform in WHOLE_CANDIDATE_PLATFORMS:
        return _verify_whole_candidate(path, family, platform, factpack or {})

    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    product = ProductContext.from_knowledge(family, platform) if family and platform else ProductContext()
    return verify_markdown(text, family=family, platform=platform, policy=policy, product=product)


def verify_markdown(
    text: str,
    *,
    family: str = "",
    platform: str,
    policy: "Policy | None" = None,
    product: "ProductContext | None" = None,
    line_offset: int = 0,
) -> VerificationReport:
    """Verify one markdown STRING's fenced code blocks for `platform`.
    Raises NotImplementedError for python/typescript -- their runners are
    whole-candidate functions that read a real file and chain-execute it
    (see module docstring); use verify_page() for those two platforms
    instead of silently degrading here."""
    if platform in WHOLE_CANDIDATE_PLATFORMS:
        raise NotImplementedError(
            f"{platform!r} verification requires a real file on disk -- use "
            "verify_page(), not verify_markdown() (python/typescript's runners are "
            "whole-candidate functions, not per-block; see module docstring)."
        )
    policy = policy or Policy.for_platform(platform)
    product = product or ProductContext()

    # A platform's fence tags are not always its runner's canonical_lang
    # (registry.py's own documented mismatch: platform "net" fences as
    # ```csharp/```cs/```c#, but DotNetRunner.canonical_lang == "csharp").
    # Fall back to {platform} itself for a platform with no registry
    # entry, so an unmapped language still reaches the honest-degradation
    # branch below instead of silently matching zero blocks.
    contract = PLATFORM_CONTRACT.get(platform)
    own_tags = contract.fence_tags if contract else frozenset({platform})

    all_blocks = enumerate_code_blocks(text, line_offset=line_offset)
    own_blocks = [b for b in all_blocks if (b.canonical_lang or b.lang) in own_tags]

    if platform not in _LANGUAGE_RUNNER_CLASSES:
        # No real runner for this platform yet (or it's not a language this
        # package runs at all) -- report every block honestly rather than
        # silently dropping it. NOT-EXECUTABLE-LANG only applies to fence
        # tags that are never code (registry.NON_EXECUTABLE_LANGS); a real
        # but unrunnable-yet language (e.g. before its own runner ships)
        # is NOT-VERIFIED, never a silent PASS.
        results = [
            BlockResult(
                identity=BlockIdentity(b.sha256_norm, b.canonical_lang or b.lang, b.index, b.start_line, b.end_line),
                status="NOT-EXECUTABLE-LANG" if (b.canonical_lang or b.lang) in NON_EXECUTABLE_LANGS else "NOT-VERIFIED",
                proof_tier=0,
            )
            for b in own_blocks
        ]
        return VerificationReport(
            runner=platform or "unknown", blocks=results,
            runners_module_version=RUNNERS_MODULE_VERSION, clone_head=product.clone_head,
        )

    runner = BaseRunner(_load_language_runner(platform, family=family))
    blocks_in = [(b.sha256_norm, (b.start_line, b.end_line), b.content) for b in own_blocks]
    options = RunOptions(
        allow_acquire=policy.allow_acquire, clone_head=product.clone_head or "",
        runners_module_version=RUNNERS_MODULE_VERSION,
    )
    results = runner.run(blocks_in, policy, product, options=options)
    return VerificationReport(
        runner=platform, blocks=results,
        runners_module_version=RUNNERS_MODULE_VERSION, clone_head=product.clone_head,
    )


def _verify_whole_candidate(path: Path, family: str, platform: str, factpack: dict) -> VerificationReport:
    factpack = dict(factpack)
    factpack.setdefault("family", family)
    factpack.setdefault("platform", platform)
    fn = _cfg_whole_candidate_runners[platform]
    raw = fn(path, factpack)

    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    all_blocks = enumerate_code_blocks(text) if text else []
    return _from_whole_candidate_dict(raw, platform, all_blocks)


def _from_whole_candidate_dict(raw: dict, platform: str, all_blocks: "list[Any]") -> VerificationReport:
    """Adapt python_verification_runner()/typescript_verification_runner()'s
    legacy dict shape into a VerificationReport. `all_blocks` is
    code_fences.py's own whole-file parse, used only for a best-effort
    line-number enrichment by position (see module docstring's disclosed
    limitation) -- never raises, falls back to (0, 0) on any mismatch."""
    blocks: list[BlockResult] = []
    for entry in raw.get("block_statuses", []):
        idx = entry["index"]
        sha = ""
        start_line = end_line = 0
        if 0 <= idx < len(all_blocks):
            enriched = all_blocks[idx]
            sha = enriched.sha256_norm
            start_line, end_line = enriched.start_line, enriched.end_line
        identity = BlockIdentity(code_sha256=sha, lang=platform, index=idx, start_line=start_line, end_line=end_line)
        status = entry.get("status")
        if status in ("PASS", "COMPILED+RAN CLEAN"):
            blocks.append(BlockResult(
                identity=identity, status="PASS", proof_tier=3,
                continues_example=bool(entry.get("continues_example", False)),
            ))
        else:
            blocks.append(BlockResult(
                identity=identity, status="BLOCKED-WITH-REASON",
                reason=entry.get("reason", "RUNTIME-ERROR"), detail=entry.get("detail", ""),
                proof_tier=3, depends_on=entry.get("depends_on"),
            ))
    env = raw.get("environment") or {}
    return VerificationReport(
        runner=raw.get("runner", platform), blocks=blocks,
        runners_module_version=RUNNERS_MODULE_VERSION,
        package=env.get("package"), package_version=env.get("version"),
        install_source=env.get("install_source"),
    )


__all__ = ["verify_page", "verify_markdown", "WHOLE_CANDIDATE_PLATFORMS"]
