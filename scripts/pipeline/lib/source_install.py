"""source_install.py -- shared source-install-mode detection (TC-PSD-HRD-10, permanent fix of
F-PSD-07). Decides, from a product's real repo layout, which install-fallback instructions the
`foss-source-install.html` partial should render for an UNPUBLISHED package. Reused by the
enrichment script that writes `data/products.json`'s `source_install_mode` field and by
`upstream_readiness_check.py`'s U-04 check (reconciliation is TC-PSD-HRD-10-03c's own slice).

Modes:
  "standard"   -- today's unconditional per-platform instructions are viable (a real manifest
                  or project file exists at the repo root).
  "pythonpath" -- python only: no packaging manifest exists, but a real importable top-level
                  package does (`pyproject.toml`/`setup.py`/`setup.cfg` absent is the F-PSD-07
                  defect itself: `pip install -e .` cannot work with no manifest at all).
  None         -- no viable install mode (preflight U-04 FAIL territory).
"""
from __future__ import annotations

from pathlib import Path

# Real-portfolio-measured (TC-PSD-HRD-10-02): a root-only check is too strict for several
# already-launched products -- 3d/net and email/net keep their .csproj/.sln under `src/`, not
# the repo root; cells/cpp's CMakeLists.txt lives inside its own `Aspose.Cells.Foss.Cpp/`
# subdirectory, not the repo root either. A bounded rglob (depth-capped, skipping vendored/
# build-output directories) is required -- the same class of fix HRD-04 already applied to
# Python's flat-layout package detection.
_MAX_MANIFEST_DEPTH = 3
_SKIP_DIR_NAMES = {".git", "node_modules", "bin", "obj", "build", "target", "dist"}

_MANIFEST_PATTERNS = {
    "typescript": ("package.json",), "javascript": ("package.json",),
    "java": ("pom.xml",), "go": ("go.mod",), "cpp": ("CMakeLists.txt",),
    "rust": ("Cargo.toml",),
}


def _has_manifest_anywhere(repo: Path, patterns: "tuple[str, ...]") -> bool:
    if not repo.is_dir():
        return False
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            depth = len(path.relative_to(repo).parts)
        except ValueError:
            continue
        if depth > _MAX_MANIFEST_DEPTH:
            continue
        name = path.name
        if any(name == pat or name.endswith(pat) for pat in patterns):
            return True
    return False


def _has_flat_importable_package(repo: Path) -> bool:
    """A root-level directory with `__init__.py`, excluding test-like names -- the same
    shape HRD-04 already fixed for `package_root.py::_detect_python_root`'s flat-layout
    branch, reimplemented here because that function's flat-layout search only runs INSIDE
    its own `if a manifest file exists` loop (confirmed live, TC-PSD-HRD-10-02) -- it never
    looks for a package at all when no manifest exists, which is exactly psd/python's case
    and the reason this card exists."""
    if not repo.is_dir():
        return False
    for child in repo.iterdir():
        if not child.is_dir():
            continue
        name_lower = child.name.lower()
        if name_lower.startswith((".", "test", "example", "doc", "api")) or name_lower.endswith("_test"):
            continue
        if (child / "__init__.py").is_file():
            return True
    return False


def _python_mode(repo: Path) -> "str | None":
    names = {p.name for p in repo.iterdir()} if repo.is_dir() else set()
    if names & {"pyproject.toml", "setup.py", "setup.cfg"}:
        return "standard"
    if _has_flat_importable_package(repo):
        return "pythonpath"
    return None


_NET_NON_PRIMARY_DIR_NAMES = {"examples", "example", "samples", "sample", "tools", "test", "tests"}


def _net_mode(repo: Path) -> "str | None":
    """Preserves the pre-existing ambiguity-sensitive rule (exactly one .sln/.slnx, or no sln
    and exactly one project file) -- a bounded existence check alone would silently treat two
    ambiguous .sln files as viable, which is wrong (nothing tells us which one to build).

    Real-portfolio-measured (TC-PSD-HRD-10-02): words/net and email/net each have real
    test/example/vendored-tool project files alongside their one real main project (e.g.
    `Aspose.Words.Tests.csproj`, `examples/msg_reader.csproj`, `Aspose.Foundation/Tools/
    XMLUnit/*.sln`) -- counting those as ambiguity candidates would wrongly mark an
    already-working repo as not viable. Filtered by the same test-name heuristic
    `package_manifest.py::_is_test_project` already uses (`"test" in stem.lower()`), plus the
    containing-directory names already excluded elsewhere in this codebase for the same reason
    (examples/samples/tools)."""
    if not repo.is_dir():
        return None
    candidates: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".sln", ".slnx", ".csproj", ".fsproj", ".vbproj"):
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            rel_parts = path.relative_to(repo).parts
        except ValueError:
            continue
        if len(rel_parts) > _MAX_MANIFEST_DEPTH:
            continue
        if "test" in path.stem.lower():
            continue
        if any(part.lower() in _NET_NON_PRIMARY_DIR_NAMES for part in rel_parts[:-1]):
            continue
        candidates.append(path)
    sln = [p for p in candidates if p.suffix.lower() in (".sln", ".slnx")]
    proj = [p for p in candidates if p.suffix.lower() in (".csproj", ".fsproj", ".vbproj")]
    if len(sln) == 1 or (not sln and len(proj) == 1):
        return "standard"
    return None


def determine_source_install_mode(platform: str, repo: Path) -> "str | None":
    if platform == "python":
        return _python_mode(repo)
    if platform == "net":
        return _net_mode(repo)
    patterns = _MANIFEST_PATTERNS.get(platform)
    if patterns is None:
        return None
    return "standard" if _has_manifest_anywhere(repo, patterns) else None
