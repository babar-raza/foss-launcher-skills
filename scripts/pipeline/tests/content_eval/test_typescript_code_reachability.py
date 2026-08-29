"""Regression tests for TC-MT040-20 (G-TS-02c, D-3): the TypeScript/JavaScript
live-fallback branch of content_eval/evaluators/_reachability.py.

Evaluator-side counterpart to TC-MT040-17's reference-filter wiring: both
consume the same lang.typescript.export_surface() barrel resolution, so a
class unreachable from the package's resolved entry point never gets a
reference page (TC-17) AND is flagged if a code example imports it anyway
(this file).

Mirrors TestRustReachability's shape in test_code_reachability.py (same
lru_cache-memoized live-fallback pattern), but exercises _reachability.py's
public functions directly rather than through a specific evaluator, since
_typescript_barrel_exports()/live_unreachable() are the actual unit this
taskcard built.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from content_eval.evaluators import _reachability


@pytest.fixture(autouse=True)
def _clear_reachability_caches():
    _reachability.clear_caches()
    yield
    _reachability.clear_caches()


def _fake_clone(monkeypatch, tmp_path: Path, family: str, platform: str) -> Path:
    """Redirect core.clone_cache.clone_path(family, platform) to a scratch dir
    under tmp_path, so live-fallback tests never touch the real clone cache.
    """
    repo_dir = tmp_path / "clone" / f"aspose_{family}_{platform}"
    repo_dir.mkdir(parents=True, exist_ok=True)

    import core.clone_cache as clone_cache_mod

    def _fake_path(fam: str, plat: str) -> Path:
        if fam == family and plat == platform:
            return repo_dir
        return Path("/nonexistent")

    monkeypatch.setattr(clone_cache_mod, "clone_path", _fake_path)
    return repo_dir


def _write_pkg_json(repo: Path, main: str = "dist/index.js") -> None:
    repo.joinpath("package.json").write_text(
        f'{{"name": "@asposefoss/fake", "main": "{main}"}}\n', encoding="utf-8"
    )


class TestTypescriptBarrelExports:

    def test_unreachable_class_not_in_barrel(self, tmp_path, monkeypatch):
        repo = _fake_clone(monkeypatch, tmp_path, "pdf", "typescript")
        _write_pkg_json(repo)
        src = repo / "src"
        src.mkdir()
        (src / "index.ts").write_text(
            "export { Document } from './document.js';\n", encoding="utf-8"
        )
        (src / "document.ts").write_text("export class Document {}\n", encoding="utf-8")
        (src / "lexer.ts").write_text("export class Lexer {}\n", encoding="utf-8")

        found, msg = _reachability.live_unreachable("Lexer", "pdf", "typescript", "typescript")
        assert found is True
        assert "Lexer" in msg
        assert "entry point" in msg

    def test_reachable_class_is_negative_control(self, tmp_path, monkeypatch):
        repo = _fake_clone(monkeypatch, tmp_path, "pdf", "typescript")
        _write_pkg_json(repo)
        src = repo / "src"
        src.mkdir()
        (src / "index.ts").write_text(
            "export { Document } from './document.js';\n", encoding="utf-8"
        )
        (src / "document.ts").write_text("export class Document {}\n", encoding="utf-8")

        found, msg = _reachability.live_unreachable("Document", "pdf", "typescript", "typescript")
        assert found is False
        assert msg == ""

    def test_javascript_language_alias_uses_same_adapter(self, tmp_path, monkeypatch):
        # live_unreachable's language arg is the extraction language string
        # ("typescript"/"javascript"); the platform is what's threaded
        # through to clone_path()/detect_package_root(), independent of it.
        repo = _fake_clone(monkeypatch, tmp_path, "pdf", "javascript")
        _write_pkg_json(repo)
        src = repo / "src"
        src.mkdir()
        (src / "index.ts").write_text("export { Document } from './document.js';\n", encoding="utf-8")
        (src / "document.ts").write_text("export class Document {}\n", encoding="utf-8")
        (src / "lexer.ts").write_text("export class Lexer {}\n", encoding="utf-8")

        found, _msg = _reachability.live_unreachable("Lexer", "pdf", "javascript", "javascript")
        assert found is True

    def test_unresolvable_entry_point_is_unknown_never_flags(self, tmp_path, monkeypatch):
        """Fail-safe: no dist/ built and no bare index.ts -- matches the real
        3d/typescript clone (live-verified 2026-08-29). Must never flag."""
        repo = _fake_clone(monkeypatch, tmp_path, "3d", "typescript")
        _write_pkg_json(repo, main="dist/index.js")  # dist/ never built
        src = repo / "src"
        src.mkdir()
        (src / "shape.ts").write_text("export class Shape {}\n", encoding="utf-8")

        found, msg = _reachability.live_unreachable("Shape", "3d", "typescript", "typescript")
        assert found is False
        assert msg == ""

    def test_missing_clone_cache_is_unknown_never_flags(self, tmp_path, monkeypatch):
        import core.clone_cache as clone_cache_mod
        monkeypatch.setattr(clone_cache_mod, "clone_path", lambda fam, plat: tmp_path / "nonexistent")

        found, msg = _reachability.live_unreachable("Anything", "pdf", "typescript", "typescript")
        assert found is False
        assert msg == ""

    def test_other_language_not_affected(self, tmp_path, monkeypatch):
        # A python/rust/csharp language string must not accidentally hit the
        # TS branch (or vice versa) -- each language's branch is independent.
        found, msg = _reachability.live_unreachable("Anything", "pdf", "python", "cpp")
        assert found is False
        assert msg == ""

    def test_barrel_exports_cached_per_family_platform(self, tmp_path, monkeypatch):
        repo = _fake_clone(monkeypatch, tmp_path, "pdf", "typescript")
        _write_pkg_json(repo)
        src = repo / "src"
        src.mkdir()
        (src / "index.ts").write_text("export { Document } from './document.js';\n", encoding="utf-8")
        (src / "document.ts").write_text("export class Document {}\n", encoding="utf-8")

        first = _reachability._typescript_barrel_exports("pdf", "typescript")
        # Mutate the fixture -- a cached call must not see this until cleared.
        (src / "index.ts").write_text("", encoding="utf-8")
        second = _reachability._typescript_barrel_exports("pdf", "typescript")
        assert first == second == frozenset({"Document"})

        _reachability.clear_caches()
        third = _reachability._typescript_barrel_exports("pdf", "typescript")
        assert third is None or "Document" not in third

    def test_non_ts_platform_returns_none(self, tmp_path, monkeypatch):
        _fake_clone(monkeypatch, tmp_path, "cells", "rust")
        assert _reachability._typescript_barrel_exports("cells", "rust") is None
