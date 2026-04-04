"""Unit tests for path_guard.py write-path allowlist guard.

Covers allowed content prefixes (all five sites, knowledge/, reports/),
forbidden prefixes and exact governance files, default deny for unknown
paths, and path normalization (backslashes, ./ prefix).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
from path_guard import check_path, _normalize


# ---------------------------------------------------------------------------
# Allowed content paths — all five sites
# ---------------------------------------------------------------------------

class TestAllowedContentPaths:
    """Paths under the five content sites should be allowed."""

    @pytest.mark.parametrize("path", [
        "content/docs.aspose.org/en/cells/python/overview.md",
        "content/docs.aspose.org/cs/cells/python/developer-guide/working-with-charts.md",
    ])
    def test_docs_site(self, path):
        decision, _ = check_path(path)
        assert decision == "ALLOW"

    @pytest.mark.parametrize("path", [
        "content/blog.aspose.org/cells/python/2024-01-01-new-release.md",
        "content/blog.aspose.org/slides/net/post.md",
    ])
    def test_blog_site(self, path):
        decision, _ = check_path(path)
        assert decision == "ALLOW"

    @pytest.mark.parametrize("path", [
        "content/kb.aspose.org/en/cells/python/faq.md",
    ])
    def test_kb_site(self, path):
        decision, _ = check_path(path)
        assert decision == "ALLOW"

    @pytest.mark.parametrize("path", [
        "content/products.aspose.org/en/cells/overview.md",
    ])
    def test_products_site(self, path):
        decision, _ = check_path(path)
        assert decision == "ALLOW"

    @pytest.mark.parametrize("path", [
        "content/reference.aspose.org/en/cells/python/api.md",
    ])
    def test_reference_site(self, path):
        decision, _ = check_path(path)
        assert decision == "ALLOW"


# ---------------------------------------------------------------------------
# Allowed knowledge/ and reports/ paths
# ---------------------------------------------------------------------------

class TestAllowedKnowledgeAndReports:

    @pytest.mark.parametrize("path", [
        "knowledge/cells/python/merged/model.yaml",
        "knowledge/slides/net/merged/api_surface.json",
    ])
    def test_knowledge_paths(self, path):
        decision, _ = check_path(path)
        assert decision == "ALLOW"

    @pytest.mark.parametrize("path", [
        "reports/2024-01-01-audit.json",
        "reports/content_eval/results.json",
    ])
    def test_reports_paths(self, path):
        decision, _ = check_path(path)
        assert decision == "ALLOW"


# ---------------------------------------------------------------------------
# Forbidden prefix paths
# ---------------------------------------------------------------------------

class TestForbiddenPrefixes:

    @pytest.mark.parametrize("path,prefix", [
        ("themes/aspose/layouts/default.html", "themes/"),
        ("layouts/partials/header.html", "layouts/"),
        ("configs/docs.aspose.org.toml", "configs/"),
        (".claude/commands/family-sync.md", ".claude/"),
        (".agents/skills/family-sync/spec.yaml", ".agents/"),
        (".kilocode/skills/family-sync/spec.yaml", ".kilocode/"),
        ("skills/family-sync.md", "skills/"),
    ])
    def test_forbidden_prefix(self, path, prefix):
        decision, reason = check_path(path)
        assert decision == "DENY"
        assert prefix in reason


# ---------------------------------------------------------------------------
# Forbidden exact governance files
# ---------------------------------------------------------------------------

class TestForbiddenExactFiles:

    @pytest.mark.parametrize("path", [
        "AGENTS.md",
        "CLAUDE.md",
        "CODEX.md",
    ])
    def test_governance_files(self, path):
        decision, reason = check_path(path)
        assert decision == "DENY"
        assert "governance" in reason


# ---------------------------------------------------------------------------
# Default deny for unknown paths
# ---------------------------------------------------------------------------

class TestDefaultDeny:

    @pytest.mark.parametrize("path", [
        "random/file.txt",
        "src/main.py",
        "static/images/logo.png",
    ])
    def test_unknown_paths_denied(self, path):
        decision, reason = check_path(path)
        assert decision == "DENY"
        assert "not in allowlist" in reason

    def test_data_path_allowed(self):
        """data/ is explicitly allowed for Hugo registry data written by update_product_registry.py."""
        decision, _ = check_path("data/something.json")
        assert decision == "ALLOW"


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

class TestPathNormalization:

    def test_backslashes_normalized(self):
        decision, _ = check_path("content\\docs.aspose.org\\en\\page.md")
        assert decision == "ALLOW"

    def test_dot_slash_stripped(self):
        decision, _ = check_path("./content/docs.aspose.org/en/page.md")
        assert decision == "ALLOW"

    def test_double_dot_slash_stripped(self):
        decision, _ = check_path("././knowledge/cells/model.yaml")
        assert decision == "ALLOW"

    def test_backslash_forbidden(self):
        decision, _ = check_path("themes\\aspose\\layout.html")
        assert decision == "DENY"

    def test_dot_slash_forbidden(self):
        decision, _ = check_path("./AGENTS.md")
        assert decision == "DENY"

    def test_normalize_helper(self):
        assert _normalize("foo\\bar\\baz") == "foo/bar/baz"
        assert _normalize("./foo/bar") == "foo/bar"
        assert _normalize("././foo") == "foo"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestCLI:

    _SCRIPT = str(Path(__file__).resolve().parent.parent / "path_guard.py")

    def test_cli_allow(self):
        result = subprocess.run(
            [sys.executable, self._SCRIPT, "content/docs.aspose.org/en/page.md"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "ALLOW" in result.stdout

    def test_cli_deny(self):
        result = subprocess.run(
            [sys.executable, self._SCRIPT, "themes/layout.html"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        assert "DENY" in result.stdout

    def test_cli_json(self):
        result = subprocess.run(
            [sys.executable, self._SCRIPT, "--json", "knowledge/cells/model.yaml"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["decision"] == "ALLOW"
        assert payload["path"] == "knowledge/cells/model.yaml"
        assert "reason" in payload

    def test_cli_json_deny(self):
        result = subprocess.run(
            [sys.executable, self._SCRIPT, "--json", "CLAUDE.md"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["decision"] == "DENY"


# ---------------------------------------------------------------------------
# Stdin batch mode (PG-01 / PG-03)
# ---------------------------------------------------------------------------

class TestStdinBatchMode:
    """--stdin mode processes all paths in one invocation."""

    _SCRIPT = str(Path(__file__).resolve().parent.parent / "path_guard.py")

    def _run_stdin(self, paths: list[str], extra_flags: list[str] | None = None) -> subprocess.CompletedProcess:
        input_text = "\n".join(paths) + ("\n" if paths else "")
        flags = extra_flags or []
        return subprocess.run(
            [sys.executable, self._SCRIPT, "--stdin"] + flags,
            input=input_text,
            capture_output=True,
            text=True,
        )

    def test_all_allow_exits_0_empty_stdout(self):
        """All-ALLOW batch → exit 0, stdout empty."""
        result = self._run_stdin([
            "content/blog.aspose.org/3d/java/test.md",
            "content/docs.aspose.org/en/cells/python/overview.md",
            "knowledge/cells/model.yaml",
        ])
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_mixed_batch_exits_2_only_deny_in_stdout(self):
        """Mixed batch → exit 2, only DENY paths in stdout."""
        result = self._run_stdin([
            "content/blog.aspose.org/3d/java/test.md",
            "skills/foo.md",
            "content/docs.aspose.org/en/overview.md",
            "AGENTS.md",
        ])
        assert result.returncode == 2
        denied = result.stdout.strip().splitlines()
        assert "skills/foo.md" in denied
        assert "AGENTS.md" in denied
        assert "content/blog.aspose.org/3d/java/test.md" not in denied
        assert "content/docs.aspose.org/en/overview.md" not in denied

    def test_all_deny_batch_exits_2_all_in_stdout(self):
        """All-DENY batch → exit 2, all three in stdout."""
        result = self._run_stdin([
            "skills/foo.md",
            "CLAUDE.md",
            "themes/bar.css",
        ])
        assert result.returncode == 2
        denied = result.stdout.strip().splitlines()
        assert len(denied) == 3
        assert "skills/foo.md" in denied
        assert "CLAUDE.md" in denied
        assert "themes/bar.css" in denied

    def test_empty_stdin_exits_0(self):
        """Empty stdin → exit 0, no output."""
        result = self._run_stdin([])
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_stdin_json_returns_array_of_deny(self):
        """--stdin --json → JSON array containing only DENY entries."""
        result = self._run_stdin(
            [
                "content/blog.aspose.org/3d/java/test.md",
                "skills/forbidden.md",
            ],
            extra_flags=["--json"],
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["path"] == "skills/forbidden.md"
        assert payload[0]["decision"] == "DENY"
        assert "reason" in payload[0]

    def test_stdin_json_all_allow_empty_array(self):
        """--stdin --json with all-ALLOW input → empty JSON array, exit 0."""
        result = self._run_stdin(
            ["content/blog.aspose.org/3d/java/test.md"],
            extra_flags=["--json"],
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload == []
