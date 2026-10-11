"""Tests for commands/ops/knowledge_git_migration.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops import knowledge_git_migration as kgm


@pytest.fixture(autouse=True)
def _configure(tmp_path, monkeypatch):
    """Isolate every test against a synthetic repo_root (configure() seam)."""
    kgm.configure(repo_root=tmp_path)
    yield
    kgm.configure(repo_root=None)


def _write_policy(repo_root: Path) -> None:
    policy_path = repo_root / "scripts" / "pipeline" / "config" / "knowledge_tracking_policy.yaml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        """
schema_version: 1
excluded_top_level_dirs:
  - _vectors
  - _overrides
keep_patterns:
  - merged/model.yaml
  - merged/api_surface.json
  - merged/snippets/**
drop_patterns:
  - scout/**
  - merged/index.json
""",
        encoding="utf-8",
    )


def _write_products(repo_root: Path, pairs) -> None:
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    entries = [{"family": f, "platform": p} for f, p in pairs]
    (data_dir / "products.json").write_text(json.dumps(entries), encoding="utf-8")


def _make_product(repo_root: Path, family: str, platform: str) -> Path:
    product_dir = repo_root / "knowledge" / family / platform
    (product_dir / "merged" / "snippets").mkdir(parents=True, exist_ok=True)
    (product_dir / "scout").mkdir(parents=True, exist_ok=True)
    (product_dir / "merged" / "model.yaml").write_text("repo_sha: abc123\n", encoding="utf-8")
    (product_dir / "merged" / "api_surface.json").write_text("{}", encoding="utf-8")
    (product_dir / "merged" / "index.json").write_text("{}", encoding="utf-8")
    (product_dir / "merged" / "snippets" / "snippet_001.cs").write_text("// x", encoding="utf-8")
    (product_dir / "scout" / "api_surface.json").write_text("{}", encoding="utf-8")
    (product_dir / "merged" / "mystery_new_file.bin").write_bytes(b"\x00\x01")
    return product_dir


class TestClassifyFile:
    def test_keep_exact_match(self):
        policy = {"keep_patterns": ["merged/model.yaml"], "drop_patterns": []}
        assert kgm.classify_file("merged/model.yaml", policy) == "KEEP"

    def test_drop_glob_match(self):
        policy = {"keep_patterns": [], "drop_patterns": ["scout/**"]}
        assert kgm.classify_file("scout/api_surface.json", policy) == "DROP"

    def test_unclassified_when_no_pattern_matches(self):
        policy = {"keep_patterns": ["merged/model.yaml"], "drop_patterns": ["scout/**"]}
        assert kgm.classify_file("merged/mystery.bin", policy) == "UNCLASSIFIED"

    def test_keep_wins_over_drop_on_ambiguous_policy(self):
        policy = {"keep_patterns": ["merged/x.json"], "drop_patterns": ["merged/x.json"]}
        assert kgm.classify_file("merged/x.json", policy) == "KEEP"

    def test_windows_backslash_path_normalized(self):
        policy = {"keep_patterns": ["merged/snippets/**"], "drop_patterns": []}
        assert kgm.classify_file("merged\\snippets\\snippet_001.cs", policy) == "KEEP"


class TestClassifyProduct:
    def test_classifies_real_files_correctly(self, tmp_path):
        _write_policy(tmp_path)
        _make_product(tmp_path, "cells", "net")
        policy = kgm.load_policy()
        row = kgm.classify_product("cells", "net", policy)
        assert "merged/model.yaml" in row["keep"]
        assert "merged/api_surface.json" in row["keep"]
        assert "merged/snippets/snippet_001.cs" in row["keep"]
        assert "scout/api_surface.json" in row["drop"]
        assert "merged/index.json" in row["drop"]
        assert "merged/mystery_new_file.bin" in row["unclassified"]
        assert row["keep_bytes"] > 0
        assert row["unclassified_bytes"] > 0

    def test_missing_product_dir_reports_not_exists(self, tmp_path):
        _write_policy(tmp_path)
        policy = kgm.load_policy()
        row = kgm.classify_product("nope", "nope", policy)
        assert row["exists"] is False
        assert row["keep"] == []
        assert row["unclassified"] == []


class TestDiscoverProducts:
    def test_only_products_with_local_knowledge_dir(self, tmp_path):
        _write_policy(tmp_path)
        _write_products(tmp_path, [("cells", "net"), ("cells", "go")])
        _make_product(tmp_path, "cells", "net")  # only cells/net has a local dir
        pairs = kgm.discover_products()
        assert pairs == [("cells", "net")]


class TestAudit:
    def test_audit_never_touches_filesystem_or_git(self, tmp_path):
        _write_policy(tmp_path)
        _write_products(tmp_path, [("cells", "net")])
        _make_product(tmp_path, "cells", "net")
        result = kgm.audit()
        assert result["totals"]["products"] == 1
        assert result["totals"]["unclassified_files"] == 1
        # untouched: file still present, nothing staged (no .git dir even created)
        assert not (tmp_path / ".git").exists()

    def test_audit_explicit_products_overrides_discovery(self, tmp_path):
        _write_policy(tmp_path)
        _make_product(tmp_path, "cells", "net")
        _make_product(tmp_path, "cells", "go")
        result = kgm.audit(products=[("cells", "net")])
        assert result["totals"]["products"] == 1
        assert result["products"][0]["family"] == "cells"


class TestApplyNeverDeletesAndIsBounded:
    def test_apply_stages_only_named_product_keep_files(self, tmp_path, monkeypatch):
        _write_policy(tmp_path)
        _make_product(tmp_path, "cells", "net")
        _make_product(tmp_path, "cells", "go")  # must remain untouched

        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)

        result = kgm.apply([("cells", "net")])
        applied = result["applied"][0]
        assert applied["family"] == "cells" and applied["platform"] == "net"
        assert set(applied["staged"]) == {"merged/model.yaml", "merged/api_surface.json",
                                           "merged/snippets/snippet_001.cs"}
        assert "merged/mystery_new_file.bin" in applied["unclassified"]

        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], cwd=str(tmp_path),
            capture_output=True, text=True, check=True,
        ).stdout
        assert "knowledge/cells/net/merged/model.yaml" in staged
        assert "knowledge/cells/go" not in staged  # untouched product

    def test_apply_never_deletes_drop_files(self, tmp_path):
        _write_policy(tmp_path)
        product_dir = _make_product(tmp_path, "cells", "net")
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)

        kgm.apply([("cells", "net")])

        assert (product_dir / "scout" / "api_surface.json").is_file()
        assert (product_dir / "merged" / "index.json").is_file()
        assert (product_dir / "merged" / "mystery_new_file.bin").is_file()


class TestFormatReport:
    def test_report_flags_unclassified(self, tmp_path):
        _write_policy(tmp_path)
        _write_products(tmp_path, [("cells", "net")])
        _make_product(tmp_path, "cells", "net")
        result = kgm.audit()
        report = kgm.format_report(result)
        assert "UNCLASSIFIED" in report
        assert "cells/net" in report


class TestCLI:
    def test_audit_exit_code_1_when_unclassified_present(self, tmp_path, capsys):
        _write_policy(tmp_path)
        _write_products(tmp_path, [("cells", "net")])
        _make_product(tmp_path, "cells", "net")
        rc = kgm.main(["audit"])
        assert rc == 1

    def test_audit_exit_code_0_when_fully_classified(self, tmp_path, capsys):
        policy_path = tmp_path / "scripts" / "pipeline" / "config" / "knowledge_tracking_policy.yaml"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(
            "schema_version: 1\nkeep_patterns: ['merged/**']\ndrop_patterns: ['scout/**']\n",
            encoding="utf-8",
        )
        _write_products(tmp_path, [("cells", "net")])
        _make_product(tmp_path, "cells", "net")
        rc = kgm.main(["audit"])
        assert rc == 0
