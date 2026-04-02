"""Tests for scripts/path_guard.py — path guard enforcement."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from path_guard import check_path, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(forbidden=None, extra=None):
    """Build a minimal config dict for tests."""
    base = {
        "forbidden_paths": forbidden if forbidden is not None else [
            "themes/", "layouts/", "configs/",
            "AGENTS.md", "CLAUDE.md", "CODEX.md",
            ".claude/", ".agents/", ".kilocode/",
            "skills/", "scripts/",
        ],
    }
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------------------
# check_path — ALLOW cases
# ---------------------------------------------------------------------------

class TestCheckPathAllow:
    def test_content_docs_path_allowed(self):
        verdict, reason = check_path(
            "content/docs.aspose.org/en/words/python/getting-started.md",
            config=_cfg(),
        )
        assert verdict == "ALLOW"
        assert reason is None

    def test_content_blog_path_allowed(self):
        verdict, _ = check_path(
            "content/blog.aspose.org/words/python/new-post.md",
            config=_cfg(),
        )
        assert verdict == "ALLOW"

    def test_knowledge_path_allowed(self):
        verdict, _ = check_path(
            "knowledge/words/python/merged/model.yaml",
            config=_cfg(),
        )
        assert verdict == "ALLOW"

    def test_reports_path_allowed(self):
        verdict, _ = check_path("reports/audit/words-python.json", config=_cfg())
        assert verdict == "ALLOW"

    def test_evidence_path_allowed(self):
        verdict, _ = check_path(
            "evidence/words/python/pef.json",
            config=_cfg(),
        )
        assert verdict == "ALLOW"

    def test_readme_allowed(self):
        verdict, _ = check_path("README.md", config=_cfg())
        assert verdict == "ALLOW"

    def test_plans_path_allowed(self):
        verdict, _ = check_path("plans/from_chat/my_plan.md", config=_cfg())
        assert verdict == "ALLOW"

    def test_empty_forbidden_list_allows_anything(self):
        verdict, _ = check_path("themes/custom.css", config={"forbidden_paths": []})
        # hardcoded list still applies
        verdict2, _ = check_path("content/page.md", config={"forbidden_paths": []})
        assert verdict2 == "ALLOW"


# ---------------------------------------------------------------------------
# check_path — DENY cases (config-driven forbidden_paths)
# ---------------------------------------------------------------------------

class TestCheckPathDeny:
    def test_themes_dir_denied(self):
        verdict, reason = check_path("themes/custom.css", config=_cfg())
        assert verdict == "DENY"
        assert "themes/" in reason

    def test_themes_subdir_denied(self):
        verdict, _ = check_path("themes/partials/header.html", config=_cfg())
        assert verdict == "DENY"

    def test_layouts_denied(self):
        verdict, _ = check_path("layouts/default.html", config=_cfg())
        assert verdict == "DENY"

    def test_configs_dir_denied(self):
        verdict, _ = check_path("configs/intake_config.yaml", config=_cfg())
        assert verdict == "DENY"

    def test_agents_md_exact_match_denied(self):
        verdict, reason = check_path("AGENTS.md", config=_cfg())
        assert verdict == "DENY"
        assert "AGENTS.md" in reason

    def test_claude_md_denied(self):
        verdict, _ = check_path("CLAUDE.md", config=_cfg())
        assert verdict == "DENY"

    def test_codex_md_denied(self):
        verdict, _ = check_path("CODEX.md", config=_cfg())
        assert verdict == "DENY"

    def test_dot_claude_dir_denied(self):
        verdict, _ = check_path(".claude/settings.json", config=_cfg())
        assert verdict == "DENY"

    def test_dot_agents_dir_denied(self):
        verdict, _ = check_path(".agents/config.yaml", config=_cfg())
        assert verdict == "DENY"

    def test_skills_dir_denied(self):
        verdict, _ = check_path("skills/new-docs-page.md", config=_cfg())
        assert verdict == "DENY"

    def test_scripts_dir_denied(self):
        verdict, _ = check_path("scripts/pipeline/audit.py", config=_cfg())
        assert verdict == "DENY"


# ---------------------------------------------------------------------------
# check_path — hardcoded safety net (overrides empty config)
# ---------------------------------------------------------------------------

class TestHardcodedForbidden:
    def test_themes_denied_even_with_empty_config(self):
        verdict, _ = check_path("themes/x.css", config={"forbidden_paths": []})
        assert verdict == "DENY"

    def test_dotgit_denied(self):
        verdict, _ = check_path(".git/config", config={"forbidden_paths": []})
        assert verdict == "DENY"

    def test_scripts_denied_even_with_empty_config(self):
        verdict, _ = check_path("scripts/evil.py", config={"forbidden_paths": []})
        assert verdict == "DENY"


# ---------------------------------------------------------------------------
# check_path — absolute path with content_root
# ---------------------------------------------------------------------------

class TestCheckPathAbsolute:
    def test_absolute_content_path_allowed(self, tmp_path):
        target = tmp_path / "content" / "docs.aspose.org" / "en" / "words" / "python" / "index.md"
        verdict, _ = check_path(str(target), content_root=tmp_path, config=_cfg())
        assert verdict == "ALLOW"

    def test_absolute_themes_path_denied(self, tmp_path):
        target = tmp_path / "themes" / "custom.css"
        verdict, _ = check_path(str(target), content_root=tmp_path, config=_cfg())
        assert verdict == "DENY"

    def test_absolute_path_outside_root_treated_as_relative(self, tmp_path):
        other_root = tmp_path / "other"
        target = tmp_path / "content" / "page.md"
        # path is not under other_root, falls back to as-is check
        verdict, _ = check_path(str(target), content_root=other_root, config=_cfg())
        # "content/page.md" is not forbidden
        assert verdict == "ALLOW"


# ---------------------------------------------------------------------------
# check_path — backslash / Windows-style path normalisation
# ---------------------------------------------------------------------------

class TestPathNormalisation:
    def test_backslash_themes_denied(self):
        verdict, _ = check_path("themes\\custom.css", config=_cfg())
        assert verdict == "DENY"

    def test_backslash_content_allowed(self):
        verdict, _ = check_path(
            "content\\docs.aspose.org\\en\\words\\python\\page.md",
            config=_cfg(),
        )
        assert verdict == "ALLOW"

    def test_trailing_slash_on_directory_denied(self):
        verdict, _ = check_path("themes/", config=_cfg())
        assert verdict == "DENY"


# ---------------------------------------------------------------------------
# check_path — custom forbidden entries in config
# ---------------------------------------------------------------------------

class TestCustomForbidden:
    def test_custom_forbidden_path_denied(self):
        cfg = _cfg(forbidden=["custom_protected/"])
        verdict, reason = check_path("custom_protected/file.txt", config=cfg)
        assert verdict == "DENY"
        assert "custom_protected/" in reason

    def test_custom_forbidden_does_not_block_unrelated_path(self):
        cfg = _cfg(forbidden=["custom_protected/"])
        # hardcoded themes/ still blocked
        verdict, _ = check_path("themes/x.css", config=cfg)
        assert verdict == "DENY"

    def test_config_forbidden_merged_with_hardcoded(self):
        cfg = _cfg(forbidden=["private/"])
        v1, _ = check_path("private/secret.yaml", config=cfg)
        v2, _ = check_path("themes/x.css", config=cfg)
        assert v1 == "DENY"
        assert v2 == "DENY"


# ---------------------------------------------------------------------------
# main() CLI — exit codes and output
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_allow_exits_0(self, capsys):
        code = main(["content/docs.aspose.org/en/words/python/page.md"])
        out = capsys.readouterr().out
        assert code == 0
        assert out.startswith("ALLOW:")

    def test_deny_exits_1(self, capsys):
        code = main(["themes/custom.css"])
        out = capsys.readouterr().out
        assert code == 1
        assert out.startswith("DENY:")

    def test_no_args_exits_2(self, capsys):
        code = main([])
        err = capsys.readouterr().err
        assert code == 2
        assert "path" in err.lower()

    def test_content_root_flag_long(self, tmp_path, capsys):
        target = str(tmp_path / "content" / "page.md")
        code = main([f"--content-root={tmp_path}", target])
        out = capsys.readouterr().out
        assert code == 0
        assert "ALLOW" in out

    def test_content_root_flag_short(self, tmp_path, capsys):
        target = str(tmp_path / "themes" / "x.css")
        code = main(["-r", str(tmp_path), target])
        out = capsys.readouterr().out
        assert code == 1
        assert "DENY" in out

    def test_deny_message_contains_path(self, capsys):
        main(["scripts/evil.py"])
        out = capsys.readouterr().out
        assert "scripts/evil.py" in out

    def test_allow_message_contains_path(self, capsys):
        main(["knowledge/words/python/merged/model.yaml"])
        out = capsys.readouterr().out
        assert "knowledge/words/python/merged/model.yaml" in out
