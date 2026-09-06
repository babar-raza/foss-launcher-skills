"""
lib/example_verification/registry.py

CONTRACT: scripts/pipeline/lib/example_verification/registry.py
  purpose: the code-side truth for what each platform's example-verification
           ceiling currently is — PLATFORM_CONTRACT, RUNNABLE_LANGS_BY_PLATFORM,
           and NON_EXECUTABLE_LANGS. `platform_capabilities.yaml`'s
           `example_verification` site (rollout step C4) mirrors this at the
           config layer; this module is the one place that actually changes
           when a runner lands (C5, C11-C14 each flip one platform's
           max_tier/precommit_blocking here in the same commit that ships
           the runner).
  inputs:  none (static data)
  outputs: PLATFORM_CONTRACT, RUNNABLE_LANGS_BY_PLATFORM, NON_EXECUTABLE_LANGS
  owner_domain: content-quality

max_tier today reflects what this package can actually prove, not an
aspiration: python/typescript already have real S-120 runners (tier 3,
ported into this package in rollout step C3); every other platform is
tier 1 (syntax-only, via syntax.py's shared tree-sitter loader, landing in
this same commit) until its own runner ships. precommit_blocking marks the
one platform (go) that already has a real, proven pre-commit compile gate
(`check_go_code_blocks.py`) predating this package entirely.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlatformContract:
    """What this package currently knows how to prove for one platform."""

    platform: str
    max_tier: int          # highest proof_tier this platform's runner can reach today
    offline_tier: int      # highest proof_tier reachable with allow_acquire=False
    runner: str | None     # runner module name under runners/, or None if unbuilt
    fence_tags: frozenset[str]   # raw markdown fence tags this platform's examples use
    precommit_blocking: bool     # True if a pre-commit hook already blocks on this platform


PLATFORM_CONTRACT: dict[str, PlatformContract] = {
    "python": PlatformContract(
        platform="python", max_tier=3, offline_tier=1, runner="python",
        fence_tags=frozenset({"python", "bash", "sh", "shell"}),
        precommit_blocking=False,
    ),
    "typescript": PlatformContract(
        platform="typescript", max_tier=3, offline_tier=1, runner="typescript",
        fence_tags=frozenset({"typescript", "ts"}),
        precommit_blocking=False,
    ),
    "go": PlatformContract(
        platform="go", max_tier=1, offline_tier=1, runner=None,
        fence_tags=frozenset({"go", "golang"}),
        precommit_blocking=True,
    ),
    "net": PlatformContract(
        platform="net", max_tier=1, offline_tier=1, runner=None,
        fence_tags=frozenset({"csharp", "cs", "c#"}),
        precommit_blocking=False,
    ),
    "java": PlatformContract(
        platform="java", max_tier=1, offline_tier=1, runner=None,
        fence_tags=frozenset({"java"}),
        precommit_blocking=False,
    ),
    "rust": PlatformContract(
        platform="rust", max_tier=1, offline_tier=1, runner=None,
        fence_tags=frozenset({"rust", "rs"}),
        precommit_blocking=False,
    ),
    "cpp": PlatformContract(
        platform="cpp", max_tier=1, offline_tier=1, runner=None,
        fence_tags=frozenset({"cpp", "c++"}),
        precommit_blocking=False,
    ),
}

# Mirrors the Phase-0 _RUNNABLE_LANGS_BY_PLATFORM dict (readme_refresh_run.py)
# plus the platforms that don't have a real runner yet -- kept here so a
# future dispatch site has one place to ask "what fence tags count as this
# platform's own examples" without re-deriving it from PLATFORM_CONTRACT
# field-by-field at every call site.
RUNNABLE_LANGS_BY_PLATFORM: dict[str, frozenset[str]] = {
    name: contract.fence_tags for name, contract in PLATFORM_CONTRACT.items()
}

# Round 3 I: fences that are never executable in any language, regardless of
# platform -- must never be reported TOOLCHAIN-UNAVAILABLE (a stub runner's
# undifferentiated fallback status, which RC13 found conflates "this is a
# genuinely missing compiler" with "this was never code to begin with").
NON_EXECUTABLE_LANGS: frozenset[str] = frozenset({
    "mermaid", "json", "yaml", "yml", "xml", "text", "txt", "console",
    "output", "diff", "ini", "toml", "properties", "markdown", "md",
    "html", "css", "sql", "plain", "log", "",
})
