"""
Tests for content_eval/evaluators/install_recipe.py (H-16 + ST-047 fix).

No test file previously existed for this evaluator (confirmed via repo-wide
search this session) despite it backing a real production gate. ST-047,
filed 2026-08-01 during the 3D-NET-REFRESH-002 remediation, found that H-16's
install-command accuracy check ran ONLY on docs.aspose.org pages -- the
19-file wrong-NuGet-command defect it should have caught spanned docs, kb,
blog, and products, so content_eval had zero visibility into 3 of the 4
surfaces. This file proves the fix: H-16 now runs on every subdomain, while
the separate "missing install instructions" INFO suggestion stays scoped to
docs/howto pages only (unchanged regression coverage).
"""

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from content_eval.evaluators.install_recipe import InstallRecipeEvaluator  # noqa: E402
from content_eval.models import Page  # noqa: E402
import content_eval.evaluators.install_recipe as _ir_mod  # noqa: E402


_TEST_REGISTRY = {
    "3d": {"net": {
        "registry_type": "nuget",
        "candidate": {"name": "Aspose.3D.Converter"},
        "candidate_owner": "asposefoss",
        "verification": {"published": True, "verified_at": None, "verified_owner": None,
                          "evidence_url": None, "method": None},
        "owner_match": None,
    }},
}


@pytest.fixture(autouse=True)
def _knowledge_root(tmp_path):
    root = tmp_path / "knowledge"
    merged = root / "3d" / "net" / "merged"
    merged.mkdir(parents=True)
    (merged / "install.md").write_text(
        "Install via NuGet: dotnet add package Aspose.3D.Converter\n",
        encoding="utf-8",
    )
    # TC-MT018-07: registry is now the primary ground truth for H-16 -- must
    # be injected explicitly (via the same configure() seam as
    # knowledge_root) so these tests stay hermetic and don't silently depend
    # on the real repo's data/package_registry.json, which drifts over time
    # independent of any code change here. _TEST_REGISTRY's "3d"/"net" entry
    # matches this fixture's install.md content on purpose, preserving this
    # file's pre-TC-MT018-07 test semantics unchanged.
    _ir_mod.configure(knowledge_root=root, registry=_TEST_REGISTRY)
    yield root
    _ir_mod.configure()  # reset to the real default (knowledge_root AND registry)


def _write_page(tmp_path, rel_path: str, body: str) -> Path:
    path = tmp_path / "content" / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


_WRONG_CMD_BODY = (
    "---\ntitle: Test\n---\n\n"
    "## Example\n\n"
    "```bash\n"
    "dotnet add package Aspose.3D.Foss\n"
    "```\n"
)

_CORRECT_CMD_BODY = (
    "---\ntitle: Test\n---\n\n"
    "## Example\n\n"
    "```bash\n"
    "dotnet add package Aspose.3D.Converter\n"
    "```\n"
)

_NO_INSTALL_BODY = (
    "---\ntitle: Test\n---\n\n"
    "## Example\n\n"
    "Use `Scene.Load` to open a file, then `Scene.Save` to write it, "
    "and `Node.CreateChildNode` to build the hierarchy.\n"
)


class TestH16RunsOnEverySubdomain:
    """ST-047: install-command accuracy must fire on kb/blog/products, not just docs."""

    def test_kb_page_wrong_command_flagged(self, tmp_path):
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/how-to-install.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1, "kb page with wrong install command should be flagged (was silently skipped pre-ST-047-fix)"

    def test_blog_page_wrong_command_flagged(self, tmp_path):
        path = _write_page(tmp_path, "blog.aspose.org/3d/net/some-post/index.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1, "blog page with wrong install command should be flagged (was silently skipped pre-ST-047-fix)"

    def test_products_page_wrong_command_flagged(self, tmp_path):
        path = _write_page(tmp_path, "products.aspose.org/en/3d/net/_index.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1, "products page with wrong install command should be flagged (was silently skipped pre-ST-047-fix)"

    def test_docs_page_wrong_command_still_flagged(self, tmp_path):
        """Regression: docs coverage (the only surface that worked before) must be unchanged."""
        path = _write_page(tmp_path, "docs.aspose.org/en/3d/net/developer-guide/usage.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1

    def test_kb_page_correct_command_not_flagged(self, tmp_path):
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/how-to-install.md", _CORRECT_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert ir == []


class TestUnregisteredFamilyPlatformIsFail:
    """TC-MT018-07: a family/platform with NO data/package_registry.json
    entry at all is no longer a silent pass the moment an install-command
    pattern actually appears -- the identical fix to
    audit/package_install_literal.py's, applied independently here since
    this evaluator feeds a different gate (no_downgrade_guard.py via
    content_eval, not the audit runner)."""

    def test_unregistered_pair_with_install_command_is_fail(self, tmp_path):
        path = _write_page(
            tmp_path, "kb.aspose.org/en/unknown-family/python/how-to-install.md",
            "---\ntitle: Test\n---\n\n```bash\npip install some-package\n```\n",
        )
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fail = [f for f in findings if f.level == "FAIL" and f.category == "IR"]
        assert len(fail) == 1
        assert "UNREGISTERED" in fail[0].message

    def test_unregistered_pair_no_install_command_still_clean(self, tmp_path):
        path = _write_page(
            tmp_path, "kb.aspose.org/en/unknown-family/python/overview.md",
            "---\ntitle: Test\n---\n\nThis page has no install instructions at all.\n",
        )
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fail = [f for f in findings if f.level == "FAIL"]
        assert fail == []

    def test_registered_pair_with_matching_command_is_not_fail(self, tmp_path):
        """Regression: the 3d/net fixture IS registered (_TEST_REGISTRY) --
        must never be caught by the unregistered-pair rule."""
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/how-to-install.md", _CORRECT_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fail = [f for f in findings if f.level == "FAIL"]
        assert fail == []


class TestWrongPlatformManagerIsUnconditional:
    """Previously this check was gated behind the same install.md-exists
    early return as the accuracy comparison, even though it has no actual
    dependency on install.md's content. TC-MT018-07 made it unconditional."""

    def test_wrong_manager_flagged_even_with_no_install_md_and_no_registry(self, tmp_path):
        path = _write_page(
            tmp_path, "kb.aspose.org/en/unknown-family/net/how-to-install.md",
            "---\ntitle: Test\n---\n\n```bash\npip install something\n```\n",
        )
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        warn = [f for f in findings if f.level == "WARN" and "package manager" in f.message.lower()]
        assert len(warn) >= 1, "pip on a .NET-platform page should be flagged regardless of install.md/registry state"


class TestPackageTokenNormalization:
    """TC-MT018-07 follow-up (2026-08-01 full-repo sweep): version-pinned,
    quoted, extras-qualified, and flag-prefixed install commands were
    generating spurious WARN mismatches once the registry check went live
    across real content, e.g. `pip install aspose-words-foss>=26.4.0`
    mismatching its own correctly-registered `aspose-words-foss` name."""

    def test_version_specifier_does_not_cause_false_mismatch(self, tmp_path):
        body = (
            "---\ntitle: Test\n---\n\n```bash\n"
            "dotnet add package Aspose.3D.Converter>=1.2.3\n```\n"
        )
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/how-to-install.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert ir == []

    def test_quoted_extras_and_version_specifier_does_not_cause_false_mismatch(self, tmp_path):
        registry = {
            "note": {"python": {
                "registry_type": "pypi",
                "candidate": {"name": "aspose-note"},
                "candidate_owner": "asposefoss",
                "verification": {"published": True, "verified_at": None, "verified_owner": None,
                                  "evidence_url": None, "method": None},
                "owner_match": None,
            }},
        }
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=registry)
        body = (
            "---\ntitle: Test\n---\n\n```bash\n"
            'pip install "aspose-note[pdf]>=26.3.2"\n```\n'
        )
        path = _write_page(tmp_path, "kb.aspose.org/en/note/python/how-to-install.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert ir == []

    def test_upgrade_flag_is_not_treated_as_the_package_name(self, tmp_path):
        """If `--upgrade` were wrongly captured as the package token instead
        of being skipped as a flag, it would mismatch the registered name
        and produce a false WARN -- confirms the flag-skip actually works,
        not just that the message text happens not to mention it."""
        registry = {
            "words": {"python": {
                "registry_type": "pypi",
                "candidate": {"name": "aspose-words-foss"},
                "candidate_owner": "asposefoss",
                "verification": {"published": True, "verified_at": None, "verified_owner": None,
                                  "evidence_url": None, "method": None},
                "owner_match": None,
            }},
        }
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=registry)
        body = (
            "---\ntitle: Test\n---\n\n```bash\n"
            "pip install --upgrade aspose-words-foss\n```\n"
        )
        path = _write_page(tmp_path, "kb.aspose.org/en/words/python/how-to-install.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert ir == [], f"--upgrade should be skipped as a flag: {ir}"


class TestMissingInstructionsSuggestionStaysDocsOnly:
    """Regression: the separate 'no install instructions' INFO suggestion must
    NOT start firing on kb/blog/products just because H-16 now runs there too."""

    def test_kb_page_no_install_no_missing_instructions_finding(self, tmp_path):
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/use-cases.md", _NO_INSTALL_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        info = [f for f in findings if f.level == "INFO"]
        assert info == [], (
            "the missing-install-instructions suggestion must stay docs-only; "
            f"got INFO findings on a kb page: {info}"
        )

    def test_docs_page_no_install_still_gets_missing_instructions_finding(self, tmp_path):
        """Regression: docs/howto pages must still get the INFO suggestion, unchanged."""
        path = _write_page(tmp_path, "docs.aspose.org/en/3d/net/developer-guide/usage.md", _NO_INSTALL_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        info = [f for f in findings if f.level == "INFO"]
        assert len(info) == 1
        assert "no installation instructions" in info[0].message.lower()

    def test_docs_index_page_still_skipped_for_missing_instructions(self, tmp_path):
        path = _write_page(tmp_path, "docs.aspose.org/en/3d/net/_index.md", _NO_INSTALL_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        assert findings == []
