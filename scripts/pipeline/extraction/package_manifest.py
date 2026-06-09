"""package_manifest.py — Extract identity fields from platform package manifests.

Extracted from scout.py (step 4.3). Contains:
- parse_manifest(repo, platform) — dispatch function
- _parse_python_manifest, _parse_dotnet_manifest, _parse_java_manifest,
  _parse_js_manifest, _parse_cpp_manifest — language-specific implementations

No Scout class dependencies — these are pure functions usable in isolation.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

LOG = logging.getLogger("scout.package_manifest")


def parse_manifest(repo: Path, platform: str) -> dict[str, Any]:
    """Extract identity fields from the platform manifest."""
    if platform == "python":
        return _parse_python_manifest(repo)
    if platform in ("net", "dotnet"):
        return _parse_dotnet_manifest(repo)
    if platform == "java":
        return _parse_java_manifest(repo)
    if platform in ("typescript", "javascript", "nodejs"):
        return _parse_js_manifest(repo)
    if platform == "cpp":
        return _parse_cpp_manifest(repo)
    if platform == "go":
        return _parse_go_manifest(repo)
    return {}


def _parse_python_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    pyp = repo / "pyproject.toml"
    if pyp.exists():
        try:
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib  # type: ignore[no-redef]
            data = tomllib.loads(pyp.read_text(encoding="utf-8", errors="replace"))
            proj = data.get("project", {})
            info["name"] = proj.get("name", "")
            info["version"] = proj.get("version", "")
            lic = proj.get("license", "")
            if isinstance(lic, dict):
                lic = lic.get("text", lic.get("file", ""))
            info["license"] = lic
            info["dependencies"] = proj.get("dependencies", [])
            info["requires_python"] = proj.get("requires-python", "")
            # Extract canonical package path for namespace packages.
            # [tool.setuptools.packages.find].include lists dotted package names;
            # the first non-wildcard entry with a dot is the canonical import root.
            # e.g. include = ["aspose.email_foss", "aspose.email_foss.*"]
            # → canonical_package = "aspose.email_foss"
            setuptools_cfg = data.get("tool", {}).get("setuptools", {})
            packages_find = setuptools_cfg.get("packages", {}).get("find", {})
            includes = packages_find.get("include", [])
            for inc in includes:
                if inc and "." in inc and not inc.endswith(".*") and not inc.endswith("*"):
                    info["canonical_package"] = inc
                    break
        except Exception as exc:
            LOG.warning("pyproject.toml parse error: %s", exc)
    if not info.get("name"):
        sp = repo / "setup.py"
        if sp.exists():
            text = sp.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'name\s*=\s*["\']([^"\']+)', text)
            if m:
                info["name"] = m.group(1)
            m = re.search(r'version\s*=\s*["\']([^"\']+)', text)
            if m:
                info["version"] = m.group(1)
    return info


def _parse_dotnet_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    csproj_files = list(repo.rglob("*.csproj"))[:20]
    if not csproj_files:
        return info
    csproj_files.sort(key=lambda p: len(p.parts))
    text = csproj_files[0].read_text(encoding="utf-8", errors="replace")
    for tag, key in [("PackageId", "name"), ("AssemblyName", "name"),
                     ("Version", "version")]:
        if key in info and info[key]:
            continue
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text)
        if m:
            info[key] = m.group(1)

    # FIX-11: Extract ALL target frameworks from multi-target csproj files.
    # <TargetFrameworks> (plural) contains semicolon-separated values;
    # <TargetFramework> (singular) contains a single value.
    m_plural = re.search(r"<TargetFrameworks>(.*?)</TargetFrameworks>", text)
    m_single = re.search(r"<TargetFramework>(.*?)</TargetFramework>", text)
    if m_plural:
        targets = [t.strip() for t in m_plural.group(1).split(";") if t.strip()]
        info["target_frameworks"] = targets
        info["target_framework"] = targets[0] if targets else ""
        # Determine minimum compatible framework
        info["min_framework"] = _lowest_dotnet_framework(targets)
    elif m_single:
        tf = m_single.group(1).strip()
        info["target_frameworks"] = [tf]
        info["target_framework"] = tf
        info["min_framework"] = tf

    return info


# Ranking for .NET framework targets (lower = broader compatibility)
_DOTNET_FRAMEWORK_RANK: dict[str, int] = {
    "netstandard1.0": 10,
    "netstandard1.1": 11,
    "netstandard1.2": 12,
    "netstandard1.3": 13,
    "netstandard1.4": 14,
    "netstandard1.5": 15,
    "netstandard1.6": 16,
    "netstandard2.0": 20,
    "netstandard2.1": 21,
    "net5.0": 50,
    "net6.0": 60,
    "net7.0": 70,
    "net8.0": 80,
    "net9.0": 90,
}


def _lowest_dotnet_framework(targets: list[str]) -> str:
    """Return the lowest (most compatible) framework from a list of targets.

    netstandard targets are ranked lower than net* targets because they
    support the widest range of runtimes. Unknown targets get rank 100.
    """
    if not targets:
        return ""
    ranked = sorted(targets, key=lambda t: _DOTNET_FRAMEWORK_RANK.get(t, 100))
    return ranked[0]


def _parse_java_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    pom = repo / "pom.xml"
    if pom.exists():
        text = pom.read_text(encoding="utf-8", errors="replace")
        for tag, key in [("groupId", "group_id"), ("artifactId", "artifact_id"),
                         ("version", "version")]:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", text)
            if m:
                info[key] = m.group(1)
        info["name"] = info.get("artifact_id", "")
        # Extract Java compiler target version (priority: release > target > source)
        for prop_tag in ["maven.compiler.release", "maven.compiler.target",
                         "maven.compiler.source"]:
            m = re.search(
                rf"<{re.escape(prop_tag)}>(.*?)</{re.escape(prop_tag)}>", text
            )
            if m:
                info["runtime_min_version"] = m.group(1).strip()
                break
    gradle = repo / "build.gradle"
    if not info.get("name") and gradle.exists():
        text = gradle.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"group\s*=\s*['\"]([^'\"]+)", text)
        if m:
            info["group_id"] = m.group(1)
        m = re.search(r"version\s*=\s*['\"]([^'\"]+)", text)
        if m:
            info["version"] = m.group(1)
    if "runtime_min_version" not in info and gradle.exists():
        text = gradle.read_text(encoding="utf-8", errors="replace")
        for pattern in [
            r"targetCompatibility\s*=\s*['\"]?(\d+)['\"]?",
            r"sourceCompatibility\s*=\s*['\"]?(\d+)['\"]?",
            r"languageVersion\.of\((\d+)\)",
        ]:
            m = re.search(pattern, text)
            if m:
                info["runtime_min_version"] = m.group(1).strip()
                break
    return info


def _parse_js_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            info["name"] = data.get("name", "")
            info["version"] = data.get("version", "")
            info["license"] = data.get("license", "")
            info["dependencies"] = list((data.get("dependencies") or {}).keys())
            info["engines_node"] = (data.get("engines") or {}).get("node", "")
        except (json.JSONDecodeError, OSError):
            pass
    return info


def _extract_go_package_name(repo: Path) -> str:
    """Return the declared package name from the first non-test .go file at repo root.

    Scans *.go files at repo root (excludes *_test.go and files in subdirs).
    Returns the package name string, or "" if none found.  Skips ``package main``.
    """
    for go_file in sorted(repo.glob("*.go")):
        if go_file.name.endswith("_test.go"):
            continue
        try:
            text = go_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^package\s+(\w+)", text, re.MULTILINE)
        if m:
            pkg = m.group(1)
            if pkg != "main":
                return pkg
    return ""


def _parse_go_manifest(repo: Path) -> dict[str, Any]:
    """Extract identity fields from go.mod."""
    info: dict[str, Any] = {}
    go_mod = repo / "go.mod"
    if not go_mod.exists():
        return info
    text = go_mod.read_text(encoding="utf-8", errors="replace")
    # Module path (first non-blank line: "module github.com/...")
    m = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
    if m:
        info["name"] = m.group(1)
    # Go version requirement
    m = re.search(r"^go\s+([\d.]+)", text, re.MULTILINE)
    if m:
        info["go_version"] = m.group(1)
        info["runtime_requirement"] = f"Go {m.group(1)}+"
    # Package name from source (distinct from module path)
    pkg_name = _extract_go_package_name(repo)
    if pkg_name:
        info["package_name"] = pkg_name
    return info


def _parse_cpp_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    cmake = repo / "CMakeLists.txt"
    if cmake.exists():
        text = cmake.read_text(encoding="utf-8", errors="replace")
        # Project name and version
        m = re.search(r"project\s*\(\s*(\S+)(?:\s+VERSION\s+(\S+))?", text,
                      re.IGNORECASE)
        if m:
            info["name"] = m.group(1)
            if m.group(2):
                info["version"] = m.group(2).rstrip(")")
        # CMake minimum required version
        m = re.search(r"cmake_minimum_required\s*\(\s*VERSION\s+([\d.]+)",
                      text, re.IGNORECASE)
        if m:
            info["cmake_min_version"] = m.group(1)
        # Library target name (first add_library call that is not INTERFACE-only)
        m = re.search(r"add_library\s*\(\s*([A-Za-z][A-Za-z0-9_.-]*)\s+", text,
                      re.IGNORECASE)
        if m:
            info["library_target"] = m.group(1)
        # C++ standard requirement
        m = re.search(r"set_property\s*\([^)]*CXX_STANDARD\s+(\d+)|"
                      r"CMAKE_CXX_STANDARD\s+(\d+)",
                      text, re.IGNORECASE)
        if m:
            std = m.group(1) or m.group(2)
            if std:
                info["cpp_standard"] = std
    return info
