"""
lib/example_verification/registry.py

CONTRACT: scripts/pipeline/lib/example_verification/registry.py
  purpose: the code-side truth for what each platform's example-verification
           ceiling currently is — PLATFORM_CONTRACT, RUNNABLE_LANGS_BY_PLATFORM,
           and NON_EXECUTABLE_LANGS. `platform_capabilities.yaml`'s
           `example_verification` site mirrors this at the config layer
           (its own parity check, check_platform_capabilities.py, diffs
           against this module).
  inputs:  none at import time other than the runner modules themselves
  outputs: PLATFORM_CONTRACT, RUNNABLE_LANGS_BY_PLATFORM, NON_EXECUTABLE_LANGS,
           RUNNER_CLASS_NAMES
  owner_domain: content-quality

MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION/TC-02: PLATFORM_CONTRACT
is now GENERATED from real runner introspection (each go/net/java/rust/cpp
LanguageRunner class's own `ceiling_tier` class attribute), not hand-typed.
Confirmed real drift this fixes: this module was last hand-edited in C2
(2026-09-06) and still claimed `max_tier=1, runner=None` for go/net/java/
rust/cpp through C5 and C11-C14, even after those taskcards shipped real
runner classes with `ceiling_tier` 3/3/3/3/2 -- the intended "C5, C11-C14
each flip one platform's max_tier here in the same commit that ships the
runner" discipline this module's own prior docstring described was never
actually followed for any of the 5. Generating from the runner classes'
own attributes makes that kind of drift structurally impossible: a runner
class change takes effect here automatically, with nothing left to
remember to update by hand.

`runner=None` still means "genuinely unbuilt" (introspection failed --
the module doesn't exist or doesn't define the expected class), never
"exists but I forgot to flip a flag."
"""
from __future__ import annotations

import importlib
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


# platform -> (runners/ module name, LanguageRunner class name). The one
# place api.py and registry.py both read this from -- api.py imports it
# from here rather than keeping its own copy, so there is exactly one
# source for "which class implements this platform's runner." Runner
# modules never import this module (confirmed: grepped every
# runners/*.py's own imports), so introspecting them here creates no
# import cycle even though api.py (which DOES import registry.py) also
# needs this same mapping.
RUNNER_CLASS_NAMES: dict[str, tuple[str, str]] = {
    "go": ("go", "GoRunner"),
    "net": ("dotnet", "DotNetRunner"),
    "java": ("java", "JavaRunner"),
    "rust": ("rust", "RustRunner"),
    "cpp": ("cpp", "CppRunner"),
}

# Fence tags and pre-commit-blocking status are policy, not something a
# runner class declares about itself -- kept as explicit data here, same
# as before TC-02. `precommit_blocking` reflects a REAL, PROVEN gate
# (check_go_code_blocks.py, pre-commit Step 18), not an aspiration; it is
# not derived from anything the runner class exposes.
_FENCE_TAGS: dict[str, frozenset[str]] = {
    "go": frozenset({"go", "golang"}),
    "net": frozenset({"csharp", "cs", "c#"}),
    "java": frozenset({"java"}),
    "rust": frozenset({"rust", "rs"}),
    "cpp": frozenset({"cpp", "c++"}),
}
_PRECOMMIT_BLOCKING: dict[str, bool] = {"go": True}


def _introspect_ceiling_tier(mod_name: str, class_name: str) -> "int | None":
    """The real LanguageRunner class's own `ceiling_tier`, or None if the
    module/class doesn't exist (genuinely unbuilt) -- read as a class
    attribute, never instantiated (every one of these 5 classes requires
    a `family` constructor argument this module has no reason to supply
    just to read a class-level constant).

    Uses a PACKAGE-RELATIVE import (`importlib.import_module(".runners.x",
    package=__package__)`), not an absolute `"example_verification.runners.x"`
    string -- confirmed live bug while building this: an absolute import
    silently fails (caught by the except below, misreporting a REAL
    runner as "genuinely unbuilt") in any caller whose sys.path has
    `scripts/pipeline` but not also `scripts/pipeline/lib` inserted --
    plausible in scripts that only set PYTHONPATH=scripts/pipeline and
    never call this package's own bootstrap header. A relative import
    resolves against this module's own `__package__` regardless of which
    sys.path prefix let Python find `example_verification` in the first
    place, so it works the same way in every caller.

    The import and the attribute lookup are deliberately in SEPARATE try
    blocks (independent-review finding on this exact taskcard): a single
    combined `except (ImportError, AttributeError)` around both would
    swallow an ImportError raised by a genuinely broken dependency INSIDE
    a runner module (e.g. a future `import some_new_lib` at module top
    level that isn't installed) the same way it swallows "module doesn't
    exist" -- silently misreporting a real, present runner as "genuinely
    unbuilt," which is the exact failure shape this function exists to
    stop happening, just from a different trigger than the one already
    fixed. No such top-level dependency exists in any of the 5 runner
    modules today (confirmed by reading each), so this doesn't change
    current behavior -- it only stops a future one from being silent."""
    try:
        mod = importlib.import_module(f".runners.{mod_name}", package=__package__)
    except ImportError:
        return None
    try:
        return getattr(mod, class_name).ceiling_tier
    except AttributeError:
        return None


def _build_platform_contract() -> dict[str, PlatformContract]:
    contract: dict[str, PlatformContract] = {
        # python/typescript: whole-candidate, S-120-ported functions
        # (runners/python.py, runners/typescript.py) -- not
        # LanguageRunner-protocol classes, so not introspectable the same
        # way (see api.py's WHOLE_CANDIDATE_PLATFORMS docstring for why).
        # Proven at real end-to-end parity against S-120 in rollout step
        # C3: real tier 3 (venv/npm install + execute).
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
    }
    for platform, (mod_name, class_name) in RUNNER_CLASS_NAMES.items():
        ceiling = _introspect_ceiling_tier(mod_name, class_name)
        contract[platform] = PlatformContract(
            platform=platform,
            max_tier=ceiling if ceiling is not None else 1,
            offline_tier=1,
            runner=mod_name if ceiling is not None else None,
            fence_tags=_FENCE_TAGS[platform],
            precommit_blocking=_PRECOMMIT_BLOCKING.get(platform, False),
        )
    return contract


PLATFORM_CONTRACT: dict[str, PlatformContract] = _build_platform_contract()

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
