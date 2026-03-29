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
                     ("Version", "version"), ("TargetFramework", "target_framework")]:
        if key in info and info[key]:
            continue
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text)
        if m:
            info[key] = m.group(1)
    return info


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


def _parse_cpp_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    cmake = repo / "CMakeLists.txt"
    if cmake.exists():
        text = cmake.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"project\s*\(\s*(\S+)(?:\s+VERSION\s+(\S+))?", text)
        if m:
            info["name"] = m.group(1)
            if m.group(2):
                info["version"] = m.group(2)
    return info
