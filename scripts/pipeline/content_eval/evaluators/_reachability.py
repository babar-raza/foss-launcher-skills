"""Shared reachability checks for code-example / reference-page identifiers.

RC-W1-004 (MT026 blind-spot audit, taskcard TC-BSA-...-04): no evaluator
checked whether an identifier used in a code example (or documented as "part
of the public API" on a reference page) is actually reachable/public for
its language, as opposed to merely existing somewhere in
``knowledge/{family}/{platform}/merged/api_surface.json``. Three confirmed
real instances (one per language):

  C#     content/docs.aspose.org/en/cells/net/developer-guide/working-with-xml-processing.md
         does ``catch (XmlParsingException ex)`` — ``XmlParsingException`` is
         declared ``internal class`` in the FOSS source and never appears in
         api_surface.json at all (is_public() already excludes it at scout
         time), so it is invisible to any check keyed on "is this class name
         known".

  Python content/docs.aspose.org/en/words/python/developer-guide/docx-writer.md
         does ``from aspose.words_foss import DocumentReader, LdmDocxWriter``
         — both classes ARE in api_surface.json (real, documented,
         syntactically public classes) but neither is in
         ``aspose/words_foss/__init__.py``'s ``__all__``, so the import
         raises ImportError for a real reader.

  Rust   content/reference.aspose.org/en/cells/rust/WorkbookModel.md documents
         ``WorkbookModel`` as "part of the public API" — it is a ``pub
         struct`` wired only via a private ``mod api;`` declaration in
         lib.rs, never re-exported via lib.rs's ``pub use api::{...}`` block,
         so no consumer of the crate can ever name it.

Two signal tiers, used together by callers:

  1. Primary — the ``reachable`` field on the api_surface.json class entry,
     set by ``scripts/pipeline/extraction/api_surface.py`` at scout time
     (Part 1 of RC-W1-004). Trusted whenever the key is present.

  2. Fallback — a best-effort LIVE check against the clone cache source tree,
     used only when the primary signal is unavailable: either the class
     entry has no ``reachable`` key at all (knowledge not yet re-scouted
     since Part 1 landed), or the class does not appear in api_surface.json
     at all (the C# `internal`-class case — is_public() excludes such
     classes from extraction entirely, so Part 1's additive field can never
     tag something that was never emitted). Every fallback degrades to
     "unknown" (no finding) on any I/O error, missing clone cache, or
     unrecognized source pattern -- it must never manufacture a false
     positive from a partial read.

Public API::

    class_reachability(class_entry)               -> bool | None
    live_unreachable(class_name, family, platform, language) -> (bool, str)

TC-MT040-42: the three live-fallback scans below now delegate their real
per-language logic to extraction/lang/<language>.py (the same adapters
extraction/api_surface.py's scout-time RC-W1-004 signal uses) instead of
maintaining an independent implementation here. Each wrapper below is
responsible only for resolving (family, platform) -> (repo, pkg_root) --
locating the right clone-cache directory and, for python/rust, the right
sub-root within it -- since the adapters' export_surface() contract takes
already-resolved Path arguments, not (family, platform) strings. See
extraction/lang/__init__.py's module docstring for the shared adapter
contract, including the C# polarity note (its export_surface() returns a
CONFIRMED-INTERNAL denylist, not a reachable allowlist, unlike python/rust).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent.parent  # scripts/pipeline
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from extraction import lang  # noqa: E402


def class_reachability(class_entry: dict | None) -> "bool | None":
    """Return the primary `reachable` signal from an api_surface.json entry.

    Returns None (unknown) when *class_entry* is None or carries no explicit
    ``reachable`` key (older knowledge, not yet re-scouted since Part 1).
    """
    if not isinstance(class_entry, dict):
        return None
    if "reachable" not in class_entry:
        return None
    return bool(class_entry["reachable"])


# ---------------------------------------------------------------------------
# Live fallback: C# — grep the clone cache for an `internal` declaration.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _csharp_internal_names(family: str, platform: str) -> frozenset:
    """Scan the clone cache once per (family, platform) for every type name
    declared `internal` (not `public`) at the top level. Returns an empty
    frozenset (never raises) if the clone cache is unavailable or unreadable.

    Real scan logic lives in extraction/lang/csharp.py's export_surface()
    (moved there, TC-MT040-42) -- this wrapper's own @lru_cache layer is
    kept (in addition to that module's own internal cache, keyed by Path)
    so a repeated (family, platform) lookup never re-pays the clone_path()
    resolution step either, matching this function's pre-TC-MT040-42
    caching characteristics exactly.
    """
    try:
        from core.clone_cache import clone_path
    except ImportError:
        return frozenset()
    repo = clone_path(family, platform)
    if not repo.is_dir():
        return frozenset()
    names, _ = lang.csharp.export_surface(repo, repo)
    return frozenset(names) if names is not None else frozenset()


# ---------------------------------------------------------------------------
# Live fallback: Python — the top-level package's own __init__.py / __all__.
# ---------------------------------------------------------------------------

def _find_python_pkg_init(repo: Path) -> "Path | None":
    """Best-effort top-level package __init__.py locator.

    Mirrors extraction/package_root.py's `_detect_python_root` at a much
    smaller scope (read-only, no scout dependency): src-layout first, then
    flat layout, then (namespace-parent case, e.g. aspose/ -> aspose/words_foss/)
    exactly one direct subdirectory carrying its own __init__.py + __all__.
    """
    candidates: list[Path] = []
    src = repo / "src"
    if src.is_dir():
        candidates.extend(p for p in src.iterdir() if p.is_dir() and (p / "__init__.py").is_file())
    if not candidates:
        try:
            candidates.extend(
                p for p in repo.iterdir()
                if p.is_dir() and (p / "__init__.py").is_file()
                and not p.name.lower().startswith((".", "test", "example", "doc", "api"))
            )
        except OSError:
            pass
    for cand in candidates:
        init = cand / "__init__.py"
        try:
            text = init.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "__all__" in text:
            return init
        # Namespace-parent layout: exactly one subdir with its own __all__.
        try:
            sub_hits = [
                c / "__init__.py" for c in cand.iterdir()
                if c.is_dir() and (c / "__init__.py").is_file()
                and "__all__" in (c / "__init__.py").read_text(encoding="utf-8", errors="ignore")
            ]
        except OSError:
            sub_hits = []
        if len(sub_hits) == 1:
            return sub_hits[0]
    return None


@lru_cache(maxsize=64)
def _python_top_level_all(family: str, platform: str) -> "frozenset | None":
    """Live-read the real top-level package's __all__ from the clone cache.

    Returns None (unknown -- never flag) when the clone cache is missing, no
    __init__.py with a recognizable __all__ can be found, or platform isn't
    python.

    Root-finding (locating the right __init__.py within *repo*) stays here
    via _find_python_pkg_init() -- this is a distinct, standalone-scoped
    algorithm from extraction/lang/python.py's own subdir-fallback search
    (that one operates on an ALREADY-RESOLVED pkg_root handed to it by
    scout's package_root.py; this one has only a bare clone-cache repo to
    start from and must find pkg_root itself). Once found, the real
    "read __all__ from this exact directory" logic is delegated to
    extraction/lang/python.py's export_surface() (TC-MT040-42) -- passing
    the located __init__.py's own parent directory as pkg_root guarantees
    that function reads __all__ directly from the very file this already
    found, reproducing the original behavior exactly without duplicating
    the __all__-parsing regex here a second time.
    """
    if platform != "python":
        return None
    try:
        from core.clone_cache import clone_path
    except ImportError:
        return None
    repo = clone_path(family, platform)
    if not repo.is_dir():
        return None
    init_path = _find_python_pkg_init(repo)
    if init_path is None:
        return None
    names, _root = lang.python.export_surface(repo, init_path.parent)
    return frozenset(names) if names is not None else None


# ---------------------------------------------------------------------------
# Live fallback: Rust — lib.rs's `pub use` re-export list.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _rust_reexported_names(family: str, platform: str) -> "frozenset | None":
    """Live-read lib.rs's `pub use` re-export list from the clone cache.

    Returns None (unknown -- never flag) when the clone cache or lib.rs is
    missing, a glob re-export defeats enumeration, or no `pub use` statement
    is found at all.

    Root-finding (preferring src/lib.rs over a top-level lib.rs, matching
    the original glob-concatenation order exactly) stays here; the real
    `pub use` regex-scan logic is delegated to extraction/lang/rust.py's
    export_surface() (TC-MT040-42).
    """
    if platform != "rust":
        return None
    try:
        from core.clone_cache import clone_path
    except ImportError:
        return None
    repo = clone_path(family, platform)
    if not repo.is_dir():
        return None
    if (repo / "src" / "lib.rs").is_file():
        pkg_root = repo / "src"
    elif (repo / "lib.rs").is_file():
        pkg_root = repo
    else:
        return None
    names, _root = lang.rust.export_surface(repo, pkg_root)
    return frozenset(names) if names is not None else None


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

def live_unreachable(class_name: str, family: str, platform: str, language: str) -> "tuple[bool, str]":
    """Best-effort live clone-cache check: is *class_name* confirmed unreachable?

    Returns ``(True, explanation)`` only when the fallback can POSITIVELY
    confirm the identifier is not part of the reachable public surface.
    Returns ``(False, "")`` for every other case, including all I/O errors
    and "can't determine" states — callers must never emit a finding from a
    (False, "") result.
    """
    if language == "csharp":
        names = _csharp_internal_names(family, platform)
        if class_name in names:
            return True, (
                f"`{class_name}` is declared `internal` in the FOSS source "
                f"(not `public`) — not part of the public API"
            )
        return False, ""
    if language == "python":
        exports = _python_top_level_all(family, platform)
        if exports is not None and class_name not in exports:
            sample = ", ".join(sorted(exports)[:6])
            return True, (
                f"`{class_name}` is not in the top-level package's `__all__` "
                f"({sample}, ...) — the import shown will raise ImportError"
            )
        return False, ""
    if language == "rust":
        reexports = _rust_reexported_names(family, platform)
        if reexports is not None and class_name not in reexports:
            return True, (
                f"`{class_name}` is not re-exported via `pub use` at the crate "
                f"root — unreachable by any consumer of the crate"
            )
        return False, ""
    return False, ""


def clear_caches() -> None:
    """Test-only: reset the lru_cache-memoized clone-cache scans.

    Clears both this module's own (family, platform)-keyed cache layer AND
    the underlying extraction/lang/ adapters' own Path-keyed cache layer
    (TC-MT040-42) -- a mutated fixture between two calls with the same
    (family, platform) would otherwise still see a stale adapter-level
    cache hit even after this module's own cache was cleared.
    """
    _csharp_internal_names.cache_clear()
    _python_top_level_all.cache_clear()
    _rust_reexported_names.cache_clear()
    lang.python.clear_cache()
    lang.rust.clear_cache()
    lang.csharp.clear_cache()
