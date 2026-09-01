"""input_manifest.py -- resolve/hash/diff generation inputs.

CONTRACT: scripts/pipeline/lib/input_manifest.py
  purpose: TC-13 slice (readme-refresh-trackb-and-followon-2026-09-01). RC-2 in the
           governing plan: "No fact carries an as-of that travels with it -- start()
           pins exactly one input (clone_cache_head). The factpack then reads 8 side
           registries... each at a different, unrecorded moment, with no recorded
           identity." tex/python's real, documented BLOCKER (this mission's own
           canary, TC-27a) was exactly this gap: data/aspose_com_targets.json was
           corrected 2026-08-24, four days after the candidate was composed, and
           nothing re-resolved or invalidated the stale Enterprise-Edition link claim.

  scope, deliberately narrow (not the full 12-input design in the governing plan's
  Target Design section): clone_cache (commit + tree SHA, generalizing the existing
  clone_cache_head-only pin) + the ONE registry with a real, documented incident,
  data/aspose_com_targets.json's own per-product entry (never the whole file -- a
  whole-file hash would make every product's approve() sensitive to every OTHER
  product's registry edit, a real false-positive-drift risk this module deliberately
  avoids). The other 7 side registries, reference_index, and banner_asset from the
  plan's full design are NOT covered here -- a disclosed, real follow-on, not silently
  assumed done. Building all 8 registries' per-product entry extraction in one pass
  was assessed as materially higher-risk (8 different real schemas, no live-verified
  extraction logic for 7 of them) than the value of doing so in this same pass,
  mirroring TC-17's own "verify before generalizing" lesson on this exact mission.

  writes: nothing on its own -- pure resolve/hash functions. The caller (readme_
          refresh_run.py's start_run()/approve()) decides what to do with the result.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root
_cfg_repo_root = _REPO_ROOT
_cfg_command_runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run


def configure(*, repo_root: "Path | str | None" = None,
              command_runner: "Callable[..., subprocess.CompletedProcess[str]] | None" = None) -> None:
    """Test seam."""
    global _cfg_repo_root, _cfg_command_runner
    _cfg_repo_root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    _cfg_command_runner = command_runner or subprocess.run


def _git(*args: str, cwd: Path) -> "str | None":
    result = _cfg_command_runner(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _resolve_ee_target_entry(family: str, platform: str) -> "dict | None":
    """The raw data/aspose_com_targets.json entry for this exact product (products.aspose.com
    platform key `{family}/{platform}`) -- deliberately the RAW registry row, not the resolved
    output of _detect_enterprise_link's own (separately, already more complex) resolution
    algorithm. This module's job is detecting whether the INPUT changed, not replicating how
    it gets consumed."""
    path = _cfg_repo_root / "data" / "aspose_com_targets.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    platforms = (data.get("targets") or {}).get("products.aspose.com", {}).get("platforms", {})
    return platforms.get(f"{family}/{platform}")


# ---------------------------------------------------------------------------
# TC-14 slice (MT061-2026-09-01-TRACKB-FOLLOWON-2, resumed from a real, disclosed PAUSE
# in the parent mission): resolve_manifest_version() -- the real "current version" source
# for a product is each product's OWN clone-cache manifest file in its native per-language
# format, never `data/package_registry.json` (confirmed live: every entry populated by the
# real, current scout mechanism -- scout_source starting "package_manifest.py:" -- has
# `candidate.version: None`; only 2 stale, pre-migration legacy rows happen to carry a
# version at all, and even those disagree with the real manifest -- cells/java's registry
# row says 26.5.0, its real pom.xml says 26.7.0). Live-registry (npm/PyPI/NuGet/Maven)
# comparison is a separate, disclosed, explicitly out-of-scope follow-on -- not attempted
# here; this module only ever reads the clone cache, never the network.
#
# Deliberately NOT built on top of `scripts/pipeline/extraction/package_manifest.py`'s
# existing `parse_manifest()` (which already extracts a bare `version` string for most
# platforms) -- that function returns one flat identity dict per platform with no file-path
# or field-level provenance, and silently omits the key entirely on any miss (empty file,
# unrecognized shape, wrong location), which cannot satisfy this taskcard's own explicit
# `{"version": None, "reason": ...}` contract for a legitimate miss. It also assumes a single
# fixed location per language (`repo / "CMakeLists.txt"`, `repo / "*.csproj"` picked by raw
# rglob order) which is demonstrably wrong for real portfolio products -- see the C++ note
# below. Reusing it here would have meant re-deriving provenance and location-search logic
# around it anyway, for no reduction in real duplicated logic; this module's own resolvers
# are self-contained instead, matching the "pure resolve/hash functions" scope already
# stated in this module's own docstring.
# ---------------------------------------------------------------------------

def _load_toml(text: str) -> dict:
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib.loads(text)
    import tomli  # type: ignore[import-not-found]
    return tomli.loads(text)


def _exclude_test_like_path(relative: Path) -> bool:
    """True when any path segment looks like a test/sample/example tree -- used to pick the
    PRODUCT's own manifest file over a nested tests/samples/examples one when a clone has more
    than one manifest file of the same kind (a real, confirmed-live shape: pdf/net's clone has
    both `src/Aspose.Pdf.Foss.csproj` and `tests/Aspose.Pdf.Foss.Tests.csproj`)."""
    lowered = [seg.lower() for seg in relative.parts]
    return any(kw in seg for seg in lowered for kw in ("test", "sample", "example"))


def _resolve_dotnet_version(clone_cache: Path) -> dict:
    try:
        candidates = list(clone_cache.rglob("*.csproj"))
    except OSError as exc:
        return {"version": None, "reason": f"could not search for .csproj files: {exc}"}
    if not candidates:
        return {"version": None, "reason": "no .csproj file found anywhere in the clone cache"}
    primary = [c for c in candidates if not _exclude_test_like_path(c.relative_to(clone_cache))]
    pool = primary or candidates
    pool.sort(key=lambda p: (len(p.relative_to(clone_cache).parts), str(p).lower()))
    target = pool[0]
    rel = target.relative_to(clone_cache).as_posix()
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"version": None, "reason": f"{rel} could not be read: {exc}"}
    m = re.search(r"<Version>(.*?)</Version>", text)
    if m and m.group(1).strip():
        return {"version": m.group(1).strip(), "source_path": rel, "source_field": "Version"}
    return {"version": None, "reason": f"{rel} found but declares no <Version> element"}


def _strip_xml_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _resolve_java_version(clone_cache: Path) -> dict:
    pom = clone_cache / "pom.xml"
    if pom.is_file():
        try:
            # Read bytes, not decoded text: every real pom.xml in this portfolio declares
            # `<?xml version="1.0" encoding="UTF-8"?>`, and ElementTree.fromstring() raises
            # ValueError on a Unicode str carrying an encoding declaration (confirmed live;
            # one product's pom.xml also has a leading UTF-8 BOM, which ElementTree handles
            # correctly from raw bytes but not after a str decode-then-re-encode round trip).
            root = ET.fromstring(pom.read_bytes())
        except (ET.ParseError, OSError) as exc:
            return {"version": None, "reason": f"pom.xml could not be parsed: {exc}"}
        # Scoped to the PROJECT's own direct-child <version> element only -- a real pom.xml
        # commonly contains many other <version> tags (dependencies, plugins, a <parent> block)
        # that a naive "first <version> in the file" scan would wrongly pick up instead.
        for child in root:
            if _strip_xml_ns(child.tag) == "version" and child.text and child.text.strip():
                return {"version": child.text.strip(), "source_path": "pom.xml",
                         "source_field": "project.version (root-level <version>, not a dependency's or plugin's)"}
        return {"version": None,
                "reason": "pom.xml has no project-level <version> element (it may inherit one from "
                          "a <parent> POM, which this pass does not resolve)"}
    gradle = clone_cache / "build.gradle"
    if gradle.is_file():
        try:
            text = gradle.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"version": None, "reason": f"build.gradle could not be read: {exc}"}
        m = re.search(r"^version\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
        if m:
            return {"version": m.group(1), "source_path": "build.gradle", "source_field": "version"}
        return {"version": None, "reason": "build.gradle found but no top-level version assignment matched"}
    return {"version": None, "reason": "no pom.xml or build.gradle found at clone cache root"}


def _extract_setup_py_version(text: str) -> "tuple[str | None, str | None]":
    """AST-first (never exec()s the file), regex fallback if the AST shape doesn't match a
    plain string literal `version=` kwarg on a `setup(...)` call."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if func_name != "setup":
                continue
            for kw in node.keywords:
                if kw.arg == "version" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    return kw.value.value, "ast:setup(version=...)"
    m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
    if m:
        return m.group(1), "regex:version=...(fallback -- AST parse failed or found no literal string kwarg)"
    return None, None


def _resolve_python_setup_py(clone_cache: Path) -> dict:
    setup_py = clone_cache / "setup.py"
    if not setup_py.is_file():
        return {"version": None, "reason": "no pyproject.toml or setup.py found at clone cache root"}
    try:
        text = setup_py.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"version": None, "reason": f"setup.py could not be read: {exc}"}
    version, method = _extract_setup_py_version(text)
    if version:
        return {"version": version, "source_path": "setup.py", "source_field": method}
    return {"version": None, "reason": "setup.py found but no version= literal could be extracted from its setup() call"}


def _resolve_dynamic_pyproject_version(clone_cache: Path, attr_ref: str) -> dict:
    """Resolves a `[tool.setuptools.dynamic] version = { attr = "pkg.module.ATTR" }` reference
    -- a real, confirmed-live shape (pdf/python) that a literal `[project].version` read alone
    would miss entirely. AST-parses the referenced module for a plain string assignment to the
    named attribute; never imports/execs the module itself."""
    if "." not in attr_ref:
        return {"version": None,
                "reason": f"dynamic version attr {attr_ref!r} is not a dotted module.attr reference"}
    module_dotted, _, attr_name = attr_ref.rpartition(".")
    module_relpath = Path(*module_dotted.split(".")).with_suffix(".py")
    candidates = [clone_cache / module_relpath, clone_cache / "src" / module_relpath]
    target = next((p for p in candidates if p.is_file()), None)
    if target is None:
        try:
            found = sorted(
                clone_cache.rglob(module_relpath.name),
                key=lambda p: len(p.relative_to(clone_cache).parts),
            )
        except OSError:
            found = []
        target = found[0] if found else None
    if target is None:
        return {"version": None,
                "reason": f"pyproject.toml declares dynamic version via attr={attr_ref!r} but no file "
                          f"matching {module_dotted}.py was found anywhere in the clone cache"}
    rel = target.relative_to(clone_cache).as_posix()
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except (OSError, SyntaxError) as exc:
        return {"version": None, "reason": f"dynamic version source {rel} could not be parsed: {exc}"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if (isinstance(t, ast.Name) and t.id == attr_name
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                return {"version": node.value.value, "source_path": rel, "source_field": f"dynamic:{attr_ref}"}
    return {"version": None,
            "reason": f"pyproject.toml declares dynamic version via attr={attr_ref!r}; found {rel} but it "
                      f"has no literal string assignment to {attr_name!r} (the real value may be computed "
                      f"at runtime -- e.g. from installed package metadata -- and is not statically resolvable)"}


def _resolve_python_version(clone_cache: Path) -> dict:
    pyproject = clone_cache / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = _load_toml(pyproject.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 -- any TOML/parse failure is a legitimate miss, not a crash
            return {"version": None, "reason": f"pyproject.toml failed to parse: {exc}"}
        project = data.get("project") or {}
        version = project.get("version")
        if isinstance(version, str) and version:
            return {"version": version, "source_path": "pyproject.toml", "source_field": "project.version"}
        dynamic = project.get("dynamic") or []
        if "version" in dynamic:
            setuptools_dynamic = ((data.get("tool") or {}).get("setuptools") or {}).get("dynamic") or {}
            dynamic_version_cfg = setuptools_dynamic.get("version")
            attr_ref = dynamic_version_cfg.get("attr") if isinstance(dynamic_version_cfg, dict) else None
            if attr_ref:
                return _resolve_dynamic_pyproject_version(clone_cache, attr_ref)
            return {"version": None,
                    "reason": "pyproject.toml declares dynamic=['version'] but no resolvable "
                              "[tool.setuptools.dynamic].version.attr mapping was found"}
        poetry = (data.get("tool") or {}).get("poetry") or {}
        poetry_version = poetry.get("version")
        if isinstance(poetry_version, str) and poetry_version:
            return {"version": poetry_version, "source_path": "pyproject.toml", "source_field": "tool.poetry.version"}
    result = _resolve_python_setup_py(clone_cache)
    if result.get("version"):
        return result
    if pyproject.is_file():
        extra = "; setup.py also present but yielded no version" if (clone_cache / "setup.py").is_file() else ""
        return {"version": None,
                "reason": "pyproject.toml has no [project].version, no resolvable dynamic version, "
                          "and no [tool.poetry].version" + extra}
    return result


def _resolve_typescript_version(clone_cache: Path) -> dict:
    pkg = clone_cache / "package.json"
    if not pkg.is_file():
        return {"version": None, "reason": "no package.json found at clone cache root"}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"version": None, "reason": f"package.json failed to parse: {exc}"}
    version = data.get("version")
    if isinstance(version, str) and version:
        return {"version": version, "source_path": "package.json", "source_field": "version"}
    return {"version": None, "reason": "package.json found but has no non-empty 'version' field"}


def _resolve_rust_version(clone_cache: Path) -> dict:
    cargo = clone_cache / "Cargo.toml"
    rel = "Cargo.toml"
    if not cargo.is_file():
        try:
            for candidate in sorted(clone_cache.iterdir()):
                if candidate.is_dir() and (candidate / "Cargo.toml").is_file():
                    cargo = candidate / "Cargo.toml"
                    rel = (Path(candidate.name) / "Cargo.toml").as_posix()
                    break
        except OSError:
            pass
    if not cargo.is_file():
        return {"version": None, "reason": "no Cargo.toml found at clone cache root or in a first-level subdirectory"}
    try:
        data = _load_toml(cargo.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return {"version": None, "reason": f"{rel} failed to parse: {exc}"}
    version = (data.get("package") or {}).get("version")
    if isinstance(version, str) and version:
        return {"version": version, "source_path": rel, "source_field": "package.version"}
    return {"version": None, "reason": f"{rel} found but [package].version is missing or empty"}


_CPP_PROJECT_RE = re.compile(r"project\s*\(\s*(\S+)(?:\s+VERSION\s+(\S+))?", re.IGNORECASE)


def _find_cpp_manifest(clone_cache: Path) -> "Path | None":
    """C++ is the one platform this survey found genuinely INCONSISTENT in file location:
    `aspose_pdf_cpp`/`aspose_email_cpp` have a top-level `CMakeLists.txt`, but `aspose_cells_cpp`
    does not -- its real one is nested at `Aspose.Cells.Foss.Cpp/CMakeLists.txt`. Searches root
    first (the common case), then the shallowest non-test/sample/example `CMakeLists.txt`
    anywhere in the clone, deterministically sorted so the result never depends on filesystem
    iteration order."""
    root = clone_cache / "CMakeLists.txt"
    if root.is_file():
        return root
    try:
        candidates = [
            p for p in clone_cache.rglob("CMakeLists.txt")
            if not _exclude_test_like_path(p.relative_to(clone_cache))
        ]
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.relative_to(clone_cache).parts), str(p).lower()))
    return candidates[0]


def _resolve_cpp_version(clone_cache: Path) -> dict:
    target = _find_cpp_manifest(clone_cache)
    if target is None:
        return {"version": None, "reason": "no CMakeLists.txt found at clone cache root or in a "
                                            "shallow non-test/sample/example subdirectory"}
    rel = target.relative_to(clone_cache).as_posix()
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"version": None, "reason": f"{rel} could not be read: {exc}"}
    m = _CPP_PROJECT_RE.search(text)
    if not m:
        return {"version": None, "reason": f"{rel} found but has no project(...) call this pass recognizes"}
    if m.group(2):
        return {"version": m.group(2).rstrip(")"), "source_path": rel, "source_field": "project(...VERSION...)"}
    # Real, confirmed-live fact, not a parsing bug: aspose_cells_cpp and aspose_slides_cpp both
    # declare `project(... LANGUAGES CXX)` with NO VERSION field at all -- this product genuinely
    # has no declared version in its manifest.
    return {"version": None, "reason": f"{rel} found but its project() call declares no VERSION field"}


def _resolve_go_version(clone_cache: Path) -> dict:
    # go.mod carries no version field in this ecosystem -- Go modules version via git tags, not
    # a manifest field. A git-tag resolver was investigated live and found unreliable in this
    # portfolio: pdf/go's real v0.5.0 tag is NOT reachable from the clone's current HEAD
    # (`git merge-base --is-ancestor v0.5.0 HEAD` fails), so `git describe --tags --always`
    # silently falls back to a bare commit hash instead of a version -- returning that hash as
    # "the version" would be actively misleading, not merely incomplete. Declared out of scope
    # for this pass, disclosed alongside the live-registry deferral, per this taskcard's own
    # explicit permission to make and record that call.
    return {"version": None,
            "reason": "go.mod declares no version field (Go modules version via git tags, not a "
                      "manifest field); git-tag-based resolution was investigated and found "
                      "unreliable in this portfolio (e.g. pdf/go's v0.5.0 tag is not an ancestor "
                      "of the clone's current HEAD, so `git describe --tags` falls back to a bare "
                      "commit hash) -- declared out of scope for this pass, alongside the "
                      "live-registry deferral, rather than risk returning a misleading value"}


_MANIFEST_VERSION_RESOLVERS: "dict[str, Callable[[Path], dict]]" = {
    "net": _resolve_dotnet_version,
    "dotnet": _resolve_dotnet_version,
    "java": _resolve_java_version,
    "python": _resolve_python_version,
    "typescript": _resolve_typescript_version,
    "javascript": _resolve_typescript_version,
    "nodejs": _resolve_typescript_version,
    "rust": _resolve_rust_version,
    "cpp": _resolve_cpp_version,
    "go": _resolve_go_version,
}


def resolve_manifest_version(family: str, platform: str, clone_cache: Path) -> dict:
    """Per-language dispatch to this product's own clone-cache manifest file, returning the real
    declared package version (never `data/package_registry.json`, which is not a reliable
    version source -- see the module-level comment above resolve_manifest_version's dispatch
    table). On success: `{"version": "26.8.0", "source_path": "...", "source_field": "..."}`.
    On a legitimate miss (file not found, field genuinely absent, format not recognized):
    `{"version": None, "reason": "..."}`. Never raises -- matching resolve_input_manifest's own
    established "a missing/unreadable input resolves to None fields, never blocks the caller"
    posture; a resolver bug is caught here and folded into the same None+reason shape rather
    than propagating.

    `family` is accepted for signature symmetry with resolve_input_manifest (and to make error
    reasons self-identifying) but is not itself needed by any resolver -- version resolution is
    purely a function of platform + the clone cache's own contents.
    """
    if not clone_cache.is_dir():
        return {"version": None, "reason": f"clone cache directory does not exist: {clone_cache}"}
    resolver = _MANIFEST_VERSION_RESOLVERS.get(platform)
    if resolver is None:
        return {"version": None,
                "reason": f"no manifest-version resolver registered for platform {platform!r} "
                          f"(family={family!r})"}
    try:
        return resolver(clone_cache)
    except Exception as exc:  # noqa: BLE001 -- a resolver bug must degrade, never crash the caller
        return {"version": None,
                "reason": f"manifest-version resolver for platform {platform!r} raised an "
                          f"unexpected error: {exc!r}"}


def resolve_input_manifest(family: str, platform: str, clone_cache: Path) -> dict:
    """Resolves and hashes this pass's in-scope input set. Returns a JSON-serializable dict;
    never raises -- a missing/unreadable input resolves to None fields rather than blocking
    resolution (the caller decides whether an all-None manifest is itself a problem).

    TC-14 (MT061-2026-09-01-TRACKB-FOLLOWON-2): adds `manifest_version`, additive alongside
    `clone_cache`/`enterprise_edition_target`, matching this module's own established
    schema-evolution style. Deliberately NOT wired into `diff_manifests` below (and therefore
    never triggers approve()'s drift-forced-replan) -- a package version legitimately changing
    between a candidate's compose and approve is expected normal product activity, not the kind
    of silent-registry-correction incident `diff_manifests` exists to catch (see TC-13/TC-27a's
    own tex/python incident), and promoting it to a replan trigger was never asked for by this
    taskcard's own scope ("manifest-parsing scope only", a new README check, not a new hard
    gate) -- a disclosed, deliberate scope boundary, not an oversight."""
    commit = _git("rev-parse", "HEAD", cwd=clone_cache) if clone_cache.is_dir() else None
    tree = _git("rev-parse", "HEAD^{tree}", cwd=clone_cache) if clone_cache.is_dir() else None
    ee_entry = _resolve_ee_target_entry(family, platform)
    ee_entry_json = json.dumps(ee_entry, sort_keys=True) if ee_entry is not None else None

    manifest = {
        "clone_cache": {"commit": commit, "tree": tree},
        "enterprise_edition_target": {
            "entry": ee_entry,
            "entry_sha256": hashlib.sha256(ee_entry_json.encode("utf-8")).hexdigest() if ee_entry_json else None,
        },
        "manifest_version": resolve_manifest_version(family, platform, clone_cache),
    }
    canonical = json.dumps(manifest, sort_keys=True)
    manifest["manifest_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return manifest


def diff_manifests(pinned: dict, current: dict) -> "list[str]":
    """Returns a list of human-readable descriptions of every field that differs -- empty
    means no drift. Named per-field (not just 'manifest_hash differs') so a drift error can
    tell the reader WHICH input moved, matching this mission's own 'named evidence' standard."""
    diffs: list[str] = []
    pinned_clone = pinned.get("clone_cache") or {}
    current_clone = current.get("clone_cache") or {}
    if pinned_clone.get("commit") != current_clone.get("commit"):
        diffs.append(
            f"clone_cache.commit: {pinned_clone.get('commit')} -> {current_clone.get('commit')}"
        )
    if pinned_clone.get("tree") != current_clone.get("tree"):
        diffs.append(
            f"clone_cache.tree: {pinned_clone.get('tree')} -> {current_clone.get('tree')}"
        )
    pinned_ee = (pinned.get("enterprise_edition_target") or {}).get("entry_sha256")
    current_ee = (current.get("enterprise_edition_target") or {}).get("entry_sha256")
    if pinned_ee != current_ee:
        diffs.append(
            "enterprise_edition_target: data/aspose_com_targets.json's entry for this product "
            f"changed (sha256 {pinned_ee} -> {current_ee})"
        )
    return diffs
