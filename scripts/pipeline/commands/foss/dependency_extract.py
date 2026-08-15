"""CONTRACT: real-manifest dependency extraction for the /readme-refresh skill (plan:
C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md,
Thirty-First incident / MT041, 2026-08-14).

Sibling module to readme_refresh_run.py/readme_refresh_checks.py (same import shape as
backlink_targets.py) -- kept separate because this is a genuinely self-contained "parse real
manifest files into normalized facts" concern (7 real ecosystem-specific parsers), matching why
scripts/pipeline/extraction/package_manifest.py already exists as its own module for a
different skill. Deliberately does NOT import or call package_manifest.py: that module belongs
to the repo-scout/knowledge pipeline with a different (knowledge-extraction-time) revision-
pinning semantics than this run's own pinned clone_cache_head, and its `dependencies:
list[str]` contract is too thin (no versions, no dev/optional split, nothing at all for
Java/.NET/C++). Its real, already-proven per-ecosystem pitfalls (csproj shortest-path file
selection, Cargo/pyproject tomllib shapes, go.mod regexes) are reused directly below, not
imported, to avoid a semantics mismatch.

Trigger: the generated cells/rust README stated "no external runtime or Microsoft Office
installation is needed" while the product's own Cargo.toml declares 7 real runtime crates
(chrono, zip, sha2, base64, serde_json, roxmltree, getrandom) -- a same-document contradiction
against that file's own, correct Intro paragraph. Root cause: knowledge/{family}/{platform}/
merged/claims.json already contains real, scout-verified "kind": "dependency" claims, but
nothing in the generation/validation machinery ever consumed them, and no part of this pipeline
ever parsed a manifest directly for README composition.

Every extractor below uses only stdlib parsing (tomllib/xml.etree.ElementTree/configparser/
json/a dedicated line-parser for go.mod) or a narrow, disclosed regex-best-effort fallback --
never a blind regex guess at manifest structure, and never `exec()`/execution of untrusted
product source (setup.py is deliberately never run).
"""

from __future__ import annotations

import configparser
import json
import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, TypedDict
from xml.etree import ElementTree

Ecosystem = Literal["cargo", "pypi", "npm", "nuget", "maven", "go_modules", "none"]
SourceType = Literal["registry", "git", "path", "vendored"]
Category = Literal["required", "optional", "native-system", "proprietary-runtime"]
Role = Literal["build", "runtime", "build+runtime"]
ExtractionConfidence = Literal["structured_parse", "regex_best_effort"]

EXTRACTOR_SCHEMA_VERSION = "dep-snapshot-v1"

# Platform -> ecosystem, matching data/package_registry.json's own real registry_type
# vocabulary verbatim (cargo/go_modules/maven/npm/nuget/pypi), for portfolio-wide consistency
# rather than inventing a second naming scheme for the same concept.
_PLATFORM_ECOSYSTEM: dict[str, Ecosystem] = {
    "rust": "cargo",
    "python": "pypi",
    "typescript": "npm",
    "javascript": "npm",
    "nodejs": "npm",
    "net": "nuget",
    "dotnet": "nuget",
    "java": "maven",
    "go": "go_modules",
    "cpp": "none",
}


class DependencyEntry(TypedDict):
    name: str
    ecosystem: Ecosystem
    version_constraint: Optional[str]
    source_type: SourceType
    category: Category
    dev_only: bool
    activating_feature: Optional[str]
    platform_condition: Optional[str]
    role: Role
    purpose: Optional[str]
    is_direct: Literal[True]
    extraction_confidence: ExtractionConfidence


class DependencySnapshot(TypedDict):
    family: str
    platform: str
    ecosystem: Ecosystem
    applicable: bool
    not_applicable_reason: Optional[str]
    required: list
    optional: list
    native_system: list
    proprietary_runtime: list
    development: list
    source_manifest_path: Optional[str]
    source_revision: Optional[str]
    extracted_at: str
    extractor_schema_version: str
    parse_errors: list


class DependencyExtractionError(RuntimeError):
    """Raised when a manifest exists but is malformed/unparseable, when a manifest is expected
    but structurally absent for an ecosystem that requires one, or when no extractor is
    registered for the platform's ecosystem. Never caught silently -- plan_run() converts this
    into a BLOCKED run via the existing _block()/ReadmeRefreshRunError mechanism (readme_
    refresh_run.py), reusing the exact shape already proven at push()'s own _block() call site.
    Deliberately NOT ReadmeRefreshRunError itself, to avoid an import cycle with run.py."""


def _entry(
    name: str, ecosystem: Ecosystem, *, version_constraint: "str | None" = None,
    source_type: SourceType = "registry", category: Category = "required",
    dev_only: bool = False, activating_feature: "str | None" = None,
    platform_condition: "str | None" = None, role: Role = "runtime",
    purpose: "str | None" = None,
    extraction_confidence: ExtractionConfidence = "structured_parse",
) -> DependencyEntry:
    return {
        "name": name, "ecosystem": ecosystem, "version_constraint": version_constraint,
        "source_type": source_type, "category": category, "dev_only": dev_only,
        "activating_feature": activating_feature, "platform_condition": platform_condition,
        "role": role, "purpose": purpose, "is_direct": True,
        "extraction_confidence": extraction_confidence,
    }


def _new_snapshot(
    family: str, platform: str, ecosystem: Ecosystem, *,
    source_manifest_path: "str | None", source_revision: "str | None",
) -> DependencySnapshot:
    return {
        "family": family, "platform": platform, "ecosystem": ecosystem,
        "applicable": True, "not_applicable_reason": None,
        "required": [], "optional": [], "native_system": [], "proprietary_runtime": [],
        "development": [],
        "source_manifest_path": source_manifest_path, "source_revision": source_revision,
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extractor_schema_version": EXTRACTOR_SCHEMA_VERSION,
        "parse_errors": [],
    }


def _place(snapshot: DependencySnapshot, entry: DependencyEntry) -> None:
    """Buckets a real entry into exactly one list -- dev_only entries land ONLY in
    `development`, never duplicated into required/optional, the direct structural fix for
    Cargo's [dev-dependencies]-must-never-leak root cause class."""
    if entry["dev_only"]:
        snapshot["development"].append(entry)
        return
    bucket = {
        "required": "required", "optional": "optional",
        "native-system": "native_system", "proprietary-runtime": "proprietary_runtime",
    }[entry["category"]]
    snapshot[bucket].append(entry)


# ---------------------------------------------------------------------------------------------
# Rust (Cargo.toml)
# ---------------------------------------------------------------------------------------------


def _extract_cargo_dependencies(
    family: str, platform: str, repo_root: Path, source_revision: "str | None",
) -> DependencySnapshot:
    manifest_path = repo_root / "Cargo.toml"
    if not manifest_path.is_file():
        raise DependencyExtractionError(f"no Cargo.toml found under {repo_root}")
    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise DependencyExtractionError(
            f"malformed Cargo.toml at {manifest_path}: {exc}"
        ) from exc

    snapshot = _new_snapshot(
        family, platform, "cargo",
        source_manifest_path="Cargo.toml", source_revision=source_revision,
    )
    features = data.get("features", {})

    def _feature_for(name: str) -> "str | None":
        for feature_name, deps in features.items():
            if any(d == f"dep:{name}" or d == name for d in deps):
                return feature_name
        # Cargo's own implicit same-named optional-dependency feature, when no [features]
        # table names it explicitly.
        return name

    def _add_table(table: dict, *, dev_only: bool, role: Role) -> None:
        for name, spec in table.items():
            if isinstance(spec, str):
                version = spec
                optional = False
            elif isinstance(spec, dict):
                version = spec.get("version")
                optional = bool(spec.get("optional", False))
            else:
                raise DependencyExtractionError(
                    f"Cargo.toml [dependencies] entry {name!r} has an unrecognized value "
                    f"type {type(spec).__name__} (expected a version string or a table)"
                )
            snapshot_role = role
            category: Category = "required"
            activating_feature = None
            if optional and not dev_only:
                category = "optional"
                activating_feature = _feature_for(name)
            _place(snapshot, _entry(
                name, "cargo", version_constraint=version, category=category,
                dev_only=dev_only, activating_feature=activating_feature,
                role=snapshot_role,
            ))

    _add_table(data.get("dependencies", {}), dev_only=False, role="runtime")
    _add_table(data.get("dev-dependencies", {}), dev_only=True, role="runtime")
    _add_table(data.get("build-dependencies", {}), dev_only=False, role="build")

    for key, table in data.items():
        if not key.startswith("target."):
            continue
        cfg = key[len("target."):].rsplit(".", 1)[0]
        target_deps = table.get("dependencies", {}) if isinstance(table, dict) else {}
        for name, spec in target_deps.items():
            version = spec if isinstance(spec, str) else (spec or {}).get("version")
            _place(snapshot, _entry(
                name, "cargo", version_constraint=version, platform_condition=cfg,
            ))

    return snapshot


# ---------------------------------------------------------------------------------------------
# Python (pyproject.toml, setup.cfg fallback)
# ---------------------------------------------------------------------------------------------

_PEP508_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$")


def _split_pep508(requirement: str) -> tuple[str, "str | None"]:
    match = _PEP508_NAME_RE.match(requirement)
    if not match:
        return requirement.strip(), None
    name = match.group(1)
    rest = match.group(2).split(";")[0].strip()  # drop environment markers
    rest = rest.strip("[]")  # crude extras-bracket strip; name itself is unaffected
    return name, (rest or None)


def _extract_pypi_dependencies(
    family: str, platform: str, repo_root: Path, source_revision: "str | None",
) -> DependencySnapshot:
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise DependencyExtractionError(
                f"malformed pyproject.toml at {pyproject}: {exc}"
            ) from exc
        snapshot = _new_snapshot(
            family, platform, "pypi",
            source_manifest_path="pyproject.toml", source_revision=source_revision,
        )
        project = data.get("project", {})
        for req in project.get("dependencies", []):
            name, version = _split_pep508(req)
            _place(snapshot, _entry(name, "pypi", version_constraint=version))
        for group, reqs in project.get("optional-dependencies", {}).items():
            dev_only = group.lower() in ("dev", "test", "tests", "development")
            for req in reqs:
                name, version = _split_pep508(req)
                _place(snapshot, _entry(
                    name, "pypi", version_constraint=version, dev_only=dev_only,
                    category="optional" if not dev_only else "required",
                    activating_feature=None if dev_only else group,
                ))
        # MT041 follow-up (found live regenerating barcode/python, 2026-08-14): the original
        # extractor only ever read [project.optional-dependencies] (PEP 621) -- a real,
        # confirmed gap for any product using the newer [dependency-groups] table (PEP 735),
        # which barcode/python's own real pyproject.toml does (`dependency-groups.dev = [
        # "pytest>=8.0", "ruff>=0.15.7"]`). Silently under-extracted with zero parse_errors --
        # worse than a raised error, since nothing signalled incompleteness. Every group under
        # this table is, by PEP 735's own design, a non-published dev/test/lint-style group --
        # always dev_only, unlike optional-dependencies groups (which can be genuine, installable,
        # user-facing extras). A group entry may also be a `{"include-group": "..."}` cross-
        # reference (PEP 735's group-composition feature) rather than a plain requirement string
        # -- skipped here, a disclosed, not-yet-implemented limitation, rather than mis-parsed.
        for group, reqs in data.get("dependency-groups", {}).items():
            for req in reqs:
                if not isinstance(req, str):
                    continue  # skip {"include-group": ...}-shaped cross-references
                name, version = _split_pep508(req)
                _place(snapshot, _entry(
                    name, "pypi", version_constraint=version, dev_only=True,
                    category="required", activating_feature=None,
                ))
        return snapshot

    setup_cfg = repo_root / "setup.cfg"
    if setup_cfg.is_file():
        parser = configparser.ConfigParser()
        try:
            parser.read(setup_cfg, encoding="utf-8")
        except configparser.Error as exc:
            raise DependencyExtractionError(
                f"malformed setup.cfg at {setup_cfg}: {exc}"
            ) from exc
        snapshot = _new_snapshot(
            family, platform, "pypi",
            source_manifest_path="setup.cfg", source_revision=source_revision,
        )
        install_requires = parser.get("options", "install_requires", fallback="")
        for line in install_requires.splitlines():
            line = line.strip()
            if not line:
                continue
            name, version = _split_pep508(line)
            _place(snapshot, _entry(
                name, "pypi", version_constraint=version,
                extraction_confidence="structured_parse",
            ))
        if parser.has_section("options.extras_require"):
            for group, reqs in parser["options.extras_require"].items():
                dev_only = group.lower() in ("dev", "test", "tests", "development")
                for line in reqs.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    name, version = _split_pep508(line)
                    _place(snapshot, _entry(
                        name, "pypi", version_constraint=version, dev_only=dev_only,
                        category="optional" if not dev_only else "required",
                        activating_feature=None if dev_only else group,
                    ))
        return snapshot

    raise DependencyExtractionError(
        f"no pyproject.toml or setup.cfg found under {repo_root} -- a setup.py-only Python "
        f"product is never parsed by executing it (a deliberate security/architecture rule, "
        f"not a parsing limitation). Add a verified entry to data/dependency_overrides.json "
        f"for {family}/{platform} if this product genuinely has no other manifest."
    )


# ---------------------------------------------------------------------------------------------
# .NET (csproj)
# ---------------------------------------------------------------------------------------------


def _select_main_csproj(repo_root: Path) -> "Path | None":
    """Reuses package_manifest.py's own proven "shortest-path csproj wins" main-library
    heuristic, reimplemented locally (not imported -- see module docstring)."""
    candidates = sorted(
        repo_root.rglob("*.csproj"), key=lambda p: len(p.relative_to(repo_root).parts)
    )
    return candidates[0] if candidates else None


def _extract_nuget_dependencies(
    family: str, platform: str, repo_root: Path, source_revision: "str | None",
) -> DependencySnapshot:
    csproj = _select_main_csproj(repo_root)
    if csproj is None:
        raise DependencyExtractionError(f"no .csproj found under {repo_root}")
    try:
        tree = ElementTree.parse(csproj)
    except ElementTree.ParseError as exc:
        raise DependencyExtractionError(f"malformed csproj at {csproj}: {exc}") from exc

    snapshot = _new_snapshot(
        family, platform, "nuget",
        source_manifest_path=str(csproj.relative_to(repo_root)).replace("\\", "/"),
        source_revision=source_revision,
    )
    for elem in tree.getroot().iter():
        if elem.tag.rsplit("}", 1)[-1] != "PackageReference":
            continue
        name = elem.get("Include") or (elem.find("Include").text if elem.find("Include") is not None else None)
        version_elem = elem.find("Version")
        version = elem.get("Version") or (version_elem.text if version_elem is not None else None)
        if not name:
            continue
        condition = elem.get("Condition")
        _place(snapshot, _entry(
            name, "nuget", version_constraint=version, platform_condition=condition,
        ))
    # An empty-but-parsed csproj is a genuine, trusted "zero dependencies" fact -- returning
    # here with an empty `required` list is correct, not an error.
    return snapshot


# ---------------------------------------------------------------------------------------------
# Java (pom.xml, Gradle fallback)
# ---------------------------------------------------------------------------------------------

_XMLNS_STRIP_RE = re.compile(r'\sxmlns="[^"]+"')
_GRADLE_DEP_RE = re.compile(
    r"(?:test)?[Ii]mplementation\s+['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]"
)


def _extract_maven_dependencies(
    family: str, platform: str, repo_root: Path, source_revision: "str | None",
) -> DependencySnapshot:
    pom = repo_root / "pom.xml"
    if pom.is_file():
        try:
            text = pom.read_text(encoding="utf-8")
            # Strip the default Maven POM xmlns so a naive `.//dependency` search doesn't
            # silently return zero results -- a real, confirmed pitfall, not speculative.
            text = _XMLNS_STRIP_RE.sub("", text, count=1)
            root = ElementTree.fromstring(text)
        except (ElementTree.ParseError, OSError) as exc:
            raise DependencyExtractionError(f"malformed pom.xml at {pom}: {exc}") from exc

        snapshot = _new_snapshot(
            family, platform, "maven",
            source_manifest_path="pom.xml", source_revision=source_revision,
        )
        deps_root = root.find("dependencies")  # never dependencyManagement -- version
        # defaults only, not real declared dependencies.
        for dep in (deps_root.findall("dependency") if deps_root is not None else []):
            group_id = dep.findtext("groupId", default="")
            artifact_id = dep.findtext("artifactId", default="")
            version = dep.findtext("version")
            scope = (dep.findtext("scope") or "").strip().lower()
            name = f"{group_id}:{artifact_id}" if group_id else artifact_id
            if not artifact_id:
                continue
            dev_only = scope == "test"
            role: Role = "build" if scope in ("provided", "system") else "runtime"
            _place(snapshot, _entry(
                name, "maven", version_constraint=version, dev_only=dev_only, role=role,
            ))
        return snapshot

    for gradle_name in ("build.gradle", "build.gradle.kts"):
        gradle = repo_root / gradle_name
        if not gradle.is_file():
            continue
        text = gradle.read_text(encoding="utf-8", errors="ignore")
        matches = _GRADLE_DEP_RE.findall(text)
        if not matches and len(text) > 200:
            raise DependencyExtractionError(
                f"{gradle} has no recognizable dependency declarations under the "
                f"regex-best-effort scan (e.g. a version-catalog libs.versions.toml dialect) "
                f"-- add a verified entry to data/dependency_overrides.json if this is real"
            )
        snapshot = _new_snapshot(
            family, platform, "maven",
            source_manifest_path=gradle_name, source_revision=source_revision,
        )
        for group_id, artifact_id, version in matches:
            name = f"{group_id}:{artifact_id}"
            dev_only = "test" in text[:text.find(f"{group_id}:{artifact_id}:{version}")][-40:].lower()
            _place(snapshot, _entry(
                name, "maven", version_constraint=version, dev_only=dev_only,
                extraction_confidence="regex_best_effort",
            ))
        return snapshot

    raise DependencyExtractionError(f"no pom.xml or build.gradle[.kts] found under {repo_root}")


# ---------------------------------------------------------------------------------------------
# Go (go.mod)
# ---------------------------------------------------------------------------------------------

_GO_REQUIRE_LINE_RE = re.compile(r"^\s*([^\s]+)\s+(v[^\s]+)(\s*//\s*indirect)?\s*$")


def _extract_go_modules_dependencies(
    family: str, platform: str, repo_root: Path, source_revision: "str | None",
) -> DependencySnapshot:
    gomod = repo_root / "go.mod"
    if not gomod.is_file():
        raise DependencyExtractionError(f"no go.mod found under {repo_root}")
    try:
        text = gomod.read_text(encoding="utf-8")
    except OSError as exc:
        raise DependencyExtractionError(f"cannot read go.mod at {gomod}: {exc}") from exc

    snapshot = _new_snapshot(
        family, platform, "go_modules",
        source_manifest_path="go.mod", source_revision=source_revision,
    )
    go_version_match = re.search(r"^go\s+([\d.]+)", text, re.MULTILINE)
    if go_version_match:
        _place(snapshot, _entry(
            "go", "go_modules", version_constraint=go_version_match.group(1),
            category="native-system", source_type="registry",
        ))

    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "require (":
            in_block = True
            continue
        if in_block and stripped == ")":
            in_block = False
            continue
        if stripped.startswith("require ") and not in_block:
            stripped = stripped[len("require "):]
        elif not in_block:
            continue
        match = _GO_REQUIRE_LINE_RE.match(stripped)
        if not match:
            continue
        module, version, indirect = match.group(1), match.group(2), match.group(3)
        if indirect:
            # A "// indirect" require is Go's own record of a TRANSITIVE dependency --
            # per the mission's explicit "never dumping the full transitive lock graph"
            # constraint, these are excluded entirely, not listed as required.
            continue
        _place(snapshot, _entry(module, "go_modules", version_constraint=version))
    return snapshot


# ---------------------------------------------------------------------------------------------
# npm / TypeScript (package.json)
# ---------------------------------------------------------------------------------------------


def _extract_npm_dependencies(
    family: str, platform: str, repo_root: Path, source_revision: "str | None",
) -> DependencySnapshot:
    package_json = repo_root / "package.json"
    if not package_json.is_file():
        raise DependencyExtractionError(f"no package.json found under {repo_root}")
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise DependencyExtractionError(f"malformed package.json at {package_json}: {exc}") from exc

    snapshot = _new_snapshot(
        family, platform, "npm",
        source_manifest_path="package.json", source_revision=source_revision,
    )
    for name, version in (data.get("dependencies") or {}).items():
        _place(snapshot, _entry(name, "npm", version_constraint=version))
    for name, version in (data.get("devDependencies") or {}).items():
        _place(snapshot, _entry(name, "npm", version_constraint=version, dev_only=True))
    for name, version in (data.get("optionalDependencies") or {}).items():
        _place(snapshot, _entry(name, "npm", version_constraint=version, category="optional"))
    # peerDependencies fold into "optional" as a disclosed simplification -- not yet
    # validated against real portfolio data (3d/typescript, the one real npm fixture in this
    # portfolio, has none).
    for name, version in (data.get("peerDependencies") or {}).items():
        _place(snapshot, _entry(name, "npm", version_constraint=version, category="optional"))
    return snapshot


# ---------------------------------------------------------------------------------------------
# C++ (CMakeLists.txt / vcpkg.json / conanfile, or genuinely no manifest)
# ---------------------------------------------------------------------------------------------

_CMAKE_FIND_PACKAGE_RE = re.compile(r"find_package\s*\(\s*(\S+)")


def _extract_cpp_dependencies(
    family: str, platform: str, repo_root: Path, source_revision: "str | None",
) -> DependencySnapshot:
    def _shallow_find(name_glob: str) -> "Path | None":
        for candidate in [repo_root / name_glob] + list(repo_root.glob(f"*/{name_glob}")):
            if candidate.is_file():
                return candidate
        return None

    vcpkg = _shallow_find("vcpkg.json")
    if vcpkg is not None:
        try:
            data = json.loads(vcpkg.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise DependencyExtractionError(f"malformed vcpkg.json at {vcpkg}: {exc}") from exc
        snapshot = _new_snapshot(
            family, platform, "none",
            source_manifest_path=str(vcpkg.relative_to(repo_root)).replace("\\", "/"),
            source_revision=source_revision,
        )
        for dep in data.get("dependencies", []):
            name = dep if isinstance(dep, str) else dep.get("name", "")
            if name:
                _place(snapshot, _entry(name, "none", source_type="registry"))
        return snapshot

    conanfile = _shallow_find("conanfile.txt")
    if conanfile is not None:
        parser = configparser.ConfigParser()
        try:
            parser.read(conanfile, encoding="utf-8")
        except configparser.Error as exc:
            raise DependencyExtractionError(f"malformed conanfile.txt at {conanfile}: {exc}") from exc
        snapshot = _new_snapshot(
            family, platform, "none",
            source_manifest_path=str(conanfile.relative_to(repo_root)).replace("\\", "/"),
            source_revision=source_revision,
        )
        if parser.has_section("requires"):
            for name in parser.options("requires"):
                _place(snapshot, _entry(name, "none", source_type="registry"))
        return snapshot

    cmake = _shallow_find("CMakeLists.txt")
    if cmake is not None:
        text = cmake.read_text(encoding="utf-8", errors="ignore")
        matches = _CMAKE_FIND_PACKAGE_RE.findall(text)
        # A real, live false positive found against cells/cpp's own genuine, dependency-free
        # CMakeLists.txt (34 lines -- compiler flags, a static-lib target, `add_subdirectory
        # (tests)` -- no find_package, no FetchContent, no ExternalProject_Add) ruled out a
        # bare file-length threshold as the "did the regex probably miss something" signal:
        # length alone doesn't distinguish "large and truly dependency-free" from "large and
        # the regex missed a real dependency." Instead, only raise when the file contains a
        # DIFFERENT dependency-management construct the narrow find_package regex doesn't
        # itself match (FetchContent/ExternalProject_Add/pkg_check_modules) -- a real signal
        # that dependency declarations exist in some form, worth a human's attention -- and
        # trust a genuine zero-match result otherwise, the same way an empty-but-parsed
        # .csproj is already trusted rather than treated as a possible miss.
        other_dep_constructs = re.search(
            r"\bFetchContent_Declare\b|\bExternalProject_Add\b|\bpkg_check_modules\b|"
            r"\bfind_library\s*\(",
            text,
        )
        if not matches and other_dep_constructs:
            raise DependencyExtractionError(
                f"{cmake} uses a dependency-management construct "
                f"({other_dep_constructs.group(0)}) this extractor doesn't yet parse -- add "
                f"a verified entry to data/dependency_overrides.json"
            )
        snapshot = _new_snapshot(
            family, platform, "none",
            source_manifest_path=str(cmake.relative_to(repo_root)).replace("\\", "/"),
            source_revision=source_revision,
        )
        for name in matches:
            _place(snapshot, _entry(
                name, "none", source_type="registry", extraction_confidence="regex_best_effort",
            ))
        return snapshot

    # Verified, earned "checked, found nothing" fact -- cells/cpp's real, confirmed state:
    # no CMakeLists.txt/vcpkg.json/conanfile.* at repo root or one level down.
    snapshot = _new_snapshot(
        family, platform, "none",
        source_manifest_path=None, source_revision=source_revision,
    )
    snapshot["applicable"] = False
    snapshot["not_applicable_reason"] = (
        "precompiled/binary-distribution C++ product -- no build-tool dependency manifest "
        "exists at the pinned revision; verified by absence of CMakeLists.txt/vcpkg.json/"
        "conanfile.* at repo root and one level down"
    )
    return snapshot


_EXTRACTORS = {
    "cargo": _extract_cargo_dependencies,
    "pypi": _extract_pypi_dependencies,
    "nuget": _extract_nuget_dependencies,
    "maven": _extract_maven_dependencies,
    "go_modules": _extract_go_modules_dependencies,
    "npm": _extract_npm_dependencies,
    "none": _extract_cpp_dependencies,
}


def _load_overrides(repo_root_of_pipeline: Path) -> dict:
    override_path = repo_root_of_pipeline / "data" / "dependency_overrides.json"
    if not override_path.is_file():
        return {}
    try:
        return json.loads(override_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def extract_dependencies(
    family: str, platform: str, clone_cache: Path, *,
    source_revision: "str | None" = None,
    pipeline_repo_root: "Path | None" = None,
) -> DependencySnapshot:
    """Dispatches on platform to the matching ecosystem extractor. `clone_cache` is the
    resolved per-product clone directory (the same argument shape `_detect_license_file
    (clone_cache: Path)` already uses). Raises DependencyExtractionError on any malformed/
    absent/unrecognized-ecosystem case -- callers (plan_run) must convert this into a real
    BLOCKED state via _block()/ReadmeRefreshRunError, never silently substitute an empty
    snapshot or a dependency-free claim.

    Checks data/dependency_overrides.json for a real, human-authored, provenance-carrying
    override -- the sanctioned escape hatch for a genuinely-unparseable-without-execution
    manifest (setup.py-only Python, a pathological CMakeLists.txt, etc.) AND for a wholly
    unregistered platform (e.g. a new-platform onboarding gap, or a test/synthetic platform),
    mirroring the established data/registry_exclusions.json/data/diagram_archetypes.json
    convention. Consulted in both failure modes -- an unregistered platform is not a special
    case exempt from the override mechanism, it is simply a more severe version of the same
    "extraction cannot proceed without help" condition.
    """
    overrides = _load_overrides(pipeline_repo_root or Path(__file__).resolve().parents[4])
    override = overrides.get(f"{family}/{platform}")

    ecosystem = _PLATFORM_ECOSYSTEM.get(platform)
    if ecosystem is None:
        if override is None:
            raise DependencyExtractionError(
                f"no ecosystem registered for platform {platform!r} -- this is a new-platform "
                f"onboarding gap, not a per-product data problem; add an entry to "
                f"dependency_extract._PLATFORM_ECOSYSTEM, or add a verified entry to "
                f"data/dependency_overrides.json for {family}/{platform}"
            )
        ecosystem = override.get("ecosystem", "none")
    else:
        try:
            return _EXTRACTORS[ecosystem](family, platform, clone_cache, source_revision)
        except DependencyExtractionError:
            if override is None:
                raise

    snapshot = _new_snapshot(
        family, platform, ecosystem,
        source_manifest_path=override.get("source_manifest_path"),
        source_revision=source_revision,
    )
    snapshot["applicable"] = override.get("applicable", True)
    snapshot["not_applicable_reason"] = override.get("not_applicable_reason")
    for bucket in ("required", "optional", "native_system", "proprietary_runtime", "development"):
        for raw in override.get(bucket, []):
            snapshot[bucket].append(_entry(
                raw["name"], ecosystem,
                version_constraint=raw.get("version_constraint"),
                category=raw.get("category", "required"),
                dev_only=(bucket == "development"),
                purpose=raw.get("purpose"),
            ))
    return snapshot


# ---------------------------------------------------------------------------------------------
# claims.json corroboration -- a real, cheap secondary staleness/scope signal, NOT independent
# data and NEVER authoritative (see readme_refresh_run.py's own docstring on this: claims.json's
# dependency claims are confirmed to be a lossy, name-only re-parse of the very same manifest,
# captured at a possibly different revision).
# ---------------------------------------------------------------------------------------------


def cross_reference_dependency_claims(
    snapshot: DependencySnapshot, claims: list, *, knowledge_repo_sha: "str | None",
) -> dict:
    """Returns {matched, manifest_only, claims_only, knowledge_revision, manifest_revision,
    same_revision}. `claims` is the raw list of real "kind": "dependency" claim dicts from
    knowledge/{family}/{platform}/merged/claims.json (each carrying a "Depends on {name}"
    text field). Never raises; a mismatch is reported, never treated as a defect on its own --
    see readme_refresh_checks.check_dependency_section_manifest_corroboration for how this
    feeds into an actual (heuristic) finding."""
    manifest_names = {
        entry["name"]
        for bucket in ("required", "optional")
        for entry in snapshot.get(bucket, [])
    }
    claim_names = set()
    for claim in claims:
        text = claim.get("text", "")
        if text.startswith("Depends on "):
            claim_names.add(text[len("Depends on "):].strip())
    manifest_revision = snapshot.get("source_revision")
    return {
        "matched": sorted(manifest_names & claim_names),
        "manifest_only": sorted(manifest_names - claim_names),
        "claims_only": sorted(claim_names - manifest_names),
        "knowledge_revision": knowledge_repo_sha,
        "manifest_revision": manifest_revision,
        "same_revision": bool(
            knowledge_repo_sha and manifest_revision and knowledge_repo_sha == manifest_revision
        ),
    }
