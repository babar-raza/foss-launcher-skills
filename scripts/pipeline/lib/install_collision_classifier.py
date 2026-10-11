"""install_collision_classifier.py -- PKGINSTALL-COLLISION-CLASSIFIER.

Codifies ST-054 TC-05's own manual method
(reports/audit/st-054-collision-classification-2026-08-16.md) into a real,
tested function instead of a hand-written Markdown report nobody's code ever
reads. That report's own method: extract real in-code identifiers (namespace/
`using` for .NET, `import`/`from...import` for Python, ES-module `import`/
`require` for TypeScript, quoted import path for Go) from
`runs/.clone_cache/{repo}`, normalize (casefold + strip non-alphanumeric),
and compare against the registry's own candidate identifier. A product is a
genuine corruption risk for the mechanical migrators
(package_install_migrator.py / package_install_inline_migrator.py) only when
a real in-code identifier normalizes to the same thing as the candidate but
is a DIFFERENT literal string -- the confirmed cells/net precedent: candidate
`Aspose.Cells.FOSS` (dotted, the real NuGet package ID) vs. real C# namespace
`Aspose.Cells_FOSS` (underscore, what code must actually import).

Re-deriving the report's own 9-of-27-flagged COLLISION_RISK set more
precisely (its own "Important caveat" section already states the reasoning
this module codifies, rather than re-inventing it): the risk is real only
when the install-command token SHAPE and the source language's own
identifier SHAPE share the same naming convention -- true only for NuGet
package IDs vs. C# `namespace`/`using` declarations (both conventionally
dotted-PascalCase, `Aspose.X.FOSS`). For pypi/npm/go_modules, a PyPI
distribution name (hyphenated) differing from its import name
(dotted/underscored) is the UNIVERSAL Python packaging convention, not a
per-product defect -- and structurally cannot be a corruption risk for these
migrators regardless, since their `_INSTALL_CMD_RE`/`_command_pattern()` only
ever match text anchored to a literal `pip install `/`npm install `/
`go get ` prefix, which never appears immediately before a bare `import`/
`require` statement in real source. Only `registry_type == "nuget"` can
produce a genuine COLLISION_RISK_STRUCTURAL verdict here.

Fail-closed, always: a missing/unreadable clone cache resolves to
COLLISION_RISK_PENDING_VERIFICATION, never a silent SAFE default -- this
module is a *scheduling gate* in front of the migrators' own already-safe
fullmatch/prefix-anchored write logic (unchanged, untouched by this module),
not a replacement for it.
"""
from __future__ import annotations

import re
import sys
from enum import Enum
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from package_registry_data import load_registry  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _CLONE_CACHE_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"


class CollisionClassification(str, Enum):
    SAFE_FOR_MECHANICAL_MIGRATION = "SAFE_FOR_MECHANICAL_MIGRATION"
    COLLISION_RISK_STRUCTURAL = "COLLISION_RISK_STRUCTURAL"
    COLLISION_RISK_PENDING_VERIFICATION = "COLLISION_RISK_PENDING_VERIFICATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # maven/cargo -- own dedicated gate


# Only registry types where the install-command token shape and the source
# language's own identifier shape share the same naming convention -- see
# module docstring. Every other registry type's normalize-match is a routine
# packaging-convention coincidence, never a real corruption path.
_STRUCTURAL_RISK_REGISTRY_TYPES = frozenset({"nuget"})

_OUT_OF_SCOPE_REGISTRY_TYPES = frozenset({"maven", "cargo"})

# Directories to never descend into -- vendored/generated trees that would
# otherwise dominate extraction with irrelevant third-party identifiers.
_EXCLUDED_DIR_NAMES = frozenset({
    "node_modules", ".git", "vendor", "dist", "build", "__pycache__",
    ".venv", "venv", "target", "bin", "obj",
})

_NET_USING_RE = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)
_PYTHON_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
_TS_IMPORT_RE = re.compile(
    r"""(?:from|require\()\s*["']([^"'.][^"']*)["']""",
)
_GO_IMPORT_PATH_RE = re.compile(r'"([\w./\-]+\.[a-z]{2,}/[\w./\-]+)"')

_EXTENSIONS_BY_PLATFORM = {
    "net": (".cs",),
    "python": (".py",),
    "typescript": (".ts", ".tsx"),
    "javascript": (".js", ".jsx"),
    "go": (".go",),
}

_PATTERN_BY_PLATFORM = {
    "net": _NET_USING_RE,
    "python": _PYTHON_IMPORT_RE,
    "typescript": _TS_IMPORT_RE,
    "javascript": _TS_IMPORT_RE,
    "go": _GO_IMPORT_PATH_RE,
}


def _iter_source_files(root: Path, extensions: tuple[str, ...]):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue
        if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        yield path


def extract_source_identifiers(clone_cache_dir: Path, platform: str) -> set[str]:
    """Extract real in-code identifiers for the given platform's source
    convention from every matching file under clone_cache_dir.

    Returns an empty set for a platform with no defined extraction pattern
    (e.g. cpp) or a clone_cache_dir with no matching files -- both are
    legitimate "nothing to compare" outcomes, distinct from a missing/
    unreadable clone_cache_dir entirely (see classify_collision_risk)."""
    pattern = _PATTERN_BY_PLATFORM.get(platform)
    extensions = _EXTENSIONS_BY_PLATFORM.get(platform)
    if pattern is None or extensions is None:
        return set()

    identifiers: set[str] = set()
    for filepath in _iter_source_files(clone_cache_dir, extensions):
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in pattern.finditer(text):
            identifiers.add(m.group(1))
    return identifiers


def normalize_identifier(token: str) -> str:
    """casefold + strip everything but letters/digits -- the exact method
    reports/audit/st-054-collision-classification-2026-08-16.md's own
    manual pass used."""
    return re.sub(r"[^a-z0-9]", "", token.casefold())


def _candidate_identifier(entry: dict) -> "str | None":
    candidate = entry.get("candidate") or {}
    return candidate.get("name") or candidate.get("module_path")


def _clone_cache_dir_for(family: str, platform: str) -> Path:
    return _CLONE_CACHE_ROOT / f"aspose_{family}_{platform}"


class ClassificationResult:
    def __init__(
        self, classification: CollisionClassification, *,
        candidate: "str | None" = None,
        colliding_identifiers: "frozenset[str] | None" = None,
        reason: str = "",
    ) -> None:
        self.classification = classification
        self.candidate = candidate
        self.colliding_identifiers = colliding_identifiers or frozenset()
        self.reason = reason

    def __repr__(self) -> str:
        return f"ClassificationResult({self.classification.value}, reason={self.reason!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, CollisionClassification):
            return self.classification == other
        if isinstance(other, ClassificationResult):
            return self.classification == other.classification
        return NotImplemented


def classify_collision_risk(
    family: str, platform: str, *,
    registry: "dict | None" = None,
    clone_cache_root: "Path | None" = None,
) -> ClassificationResult:
    """Fail-closed: any parse/extraction/lookup error resolves to
    COLLISION_RISK_PENDING_VERIFICATION, never a silent SAFE default."""
    reg = registry if registry is not None else load_registry()
    entry = (reg.get(family) or {}).get(platform)
    if not isinstance(entry, dict):
        return ClassificationResult(
            CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION,
            reason=f"no data/package_registry.json entry for {family}/{platform}",
        )

    registry_type = entry.get("registry_type")
    if registry_type in _OUT_OF_SCOPE_REGISTRY_TYPES:
        return ClassificationResult(
            CollisionClassification.NOT_APPLICABLE,
            reason=f"{registry_type} has its own dedicated migration gate",
        )

    candidate = _candidate_identifier(entry)
    if not candidate:
        return ClassificationResult(
            CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION,
            reason="registry entry has no candidate name/module_path to compare against",
        )

    cache_root = clone_cache_root if clone_cache_root is not None else _CLONE_CACHE_ROOT
    clone_cache_dir = cache_root / f"aspose_{family}_{platform}"
    if not clone_cache_dir.is_dir():
        return ClassificationResult(
            CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION,
            candidate=candidate,
            reason=f"no local clone cache at {clone_cache_dir} -- cannot verify against real source",
        )

    try:
        real_identifiers = extract_source_identifiers(clone_cache_dir, platform)
    except OSError as exc:
        return ClassificationResult(
            CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION,
            candidate=candidate,
            reason=f"extraction failed: {exc!r}",
        )

    normalized_candidate = normalize_identifier(candidate)
    colliding = frozenset(
        ident for ident in real_identifiers
        if ident != candidate and normalize_identifier(ident) == normalized_candidate
    )

    if not colliding:
        return ClassificationResult(
            CollisionClassification.SAFE_FOR_MECHANICAL_MIGRATION,
            candidate=candidate,
            reason=f"no real in-code identifier collides with candidate {candidate!r}",
        )

    if registry_type in _STRUCTURAL_RISK_REGISTRY_TYPES:
        return ClassificationResult(
            CollisionClassification.COLLISION_RISK_STRUCTURAL,
            candidate=candidate,
            colliding_identifiers=colliding,
            reason=(
                f"{registry_type} install-token shape and this language's own identifier "
                f"shape share the same naming convention -- {sorted(colliding)} normalize-match "
                f"candidate {candidate!r} but are different literal strings"
            ),
        )

    return ClassificationResult(
        CollisionClassification.SAFE_FOR_MECHANICAL_MIGRATION,
        candidate=candidate,
        colliding_identifiers=colliding,
        reason=(
            f"{sorted(colliding)} normalize-match candidate {candidate!r} but this is a "
            f"routine {registry_type} packaging-convention divergence, not a structural risk -- "
            "the prefix-anchored install-command regex can never match inside an import/require "
            "statement regardless"
        ),
    )
