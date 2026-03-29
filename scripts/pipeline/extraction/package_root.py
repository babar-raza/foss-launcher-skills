"""package_root.py — Detect the source root of a FOSS package repository.

Extracted from scout.py (step 4.2). Contains:
- detect_package_root(repo, platform) — dispatch function
- _detect_python_root, _detect_dotnet_root, _detect_java_root,
  _detect_js_root, _detect_cpp_root — language-specific implementations

No Scout class dependencies — these are pure functions usable in isolation.
"""
from __future__ import annotations

import json
from pathlib import Path


def detect_package_root(repo: Path, platform: str) -> Path:
    """Return the package source root inside *repo*."""
    if platform == "python":
        return _detect_python_root(repo)
    if platform in ("net", "dotnet"):
        return _detect_dotnet_root(repo)
    if platform == "java":
        return _detect_java_root(repo)
    if platform in ("typescript", "javascript", "nodejs"):
        return _detect_js_root(repo, platform)
    if platform == "cpp":
        return _detect_cpp_root(repo)
    return repo


def _detect_python_root(repo: Path) -> Path:
    for marker in ("pyproject.toml", "setup.py", "setup.cfg"):
        if (repo / marker).exists():
            # look for src layout first
            src = repo / "src"
            if src.is_dir():
                pkgs = [d for d in src.iterdir() if d.is_dir()
                        and (d / "__init__.py").exists()]
                if pkgs:
                    return pkgs[0]
            # flat layout: first package dir at root
            pkgs = [d for d in repo.iterdir() if d.is_dir()
                    and (d / "__init__.py").exists()
                    and not d.name.startswith((".", "test", "example", "doc"))]
            if pkgs:
                return pkgs[0]
    return repo


def _detect_dotnet_root(repo: Path) -> Path:
    csproj_files = list(repo.rglob("*.csproj"))[:50]
    if not csproj_files:
        return repo
    # exclude test and exe projects
    candidates = []
    for cp in csproj_files:
        text = cp.read_text(encoding="utf-8", errors="replace").lower()
        if "test" in cp.stem.lower():
            continue
        if "<outputtype>exe</outputtype>" in text:
            continue
        candidates.append(cp)
    if not candidates:
        candidates = csproj_files
    # prefer shortest path (most likely the primary library project)
    candidates.sort(key=lambda p: len(p.parts))
    return candidates[0].parent


def _detect_java_root(repo: Path) -> Path:
    for candidate in ("src/main/java", "app/src/main/java", "src"):
        p = repo / candidate
        if p.is_dir():
            return p
    return repo


def _detect_js_root(repo: Path, platform: str) -> Path:
    pkg_json = repo / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            for field in ("main", "module"):
                val = data.get(field, "")
                if val:
                    p = repo / val
                    if p.exists():
                        return p.parent
            exports = data.get("exports", {})
            if isinstance(exports, dict):
                dot = exports.get(".", {})
                if isinstance(dot, dict):
                    for key in ("import", "require", "default"):
                        val = dot.get(key, "")
                        if val and (repo / val).exists():
                            return (repo / val).parent
                elif isinstance(dot, str) and (repo / dot).exists():
                    return (repo / dot).parent
        except (json.JSONDecodeError, OSError):
            pass
    for d in ("src", "lib", "dist"):
        if (repo / d).is_dir():
            return repo / d
    return repo


def _detect_cpp_root(repo: Path) -> Path:
    inc = repo / "include"
    if inc.is_dir():
        return inc
    src = repo / "src"
    if src.is_dir():
        return src
    return repo
