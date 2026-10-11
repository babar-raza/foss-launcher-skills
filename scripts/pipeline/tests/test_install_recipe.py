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


class TestPublishChannelClaimsMatchVerificationPublished:
    """RC-W1-003 (Mission MT026-2026-08-09-BLIND-SPOT-AUDIT-WAVE1,
    TC-BSA-bsa-20260809T044618Z-5891c467551a-03): _verify_install_accuracy
    already loads data/package_registry.json's verification block for every
    page it checks, but only ever cross-referenced candidate.name -- never
    verification.published. Real confirmed defect: barcode/python's
    verification.published is false (data/package_registry.json, backfilled
    2026-08-01, no live PyPI match found), yet its getting-started pages
    across 5 subdomains / 57 files confidently claim the package "is
    published on PyPI" / link to a PyPI project page. These tests use
    barcode/python's real registry state as the negative fixture, and a
    published:true product as the positive (no-false-positive) case.
    """

    # Mirrors data/package_registry.json's real barcode.python entry
    # (verified 2026-08-01: "no live match found for any tried candidate;
    # recorded as not-yet-published with the best available candidate name").
    _BARCODE_PYTHON_REGISTRY = {
        "barcode": {"python": {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-barcode-foss"},
            "candidate_owner": "asposefoss",
            "verification": {
                "published": False,
                "verified_at": "2026-08-01",
                "verified_owner": None,
                "evidence_url": None,
                "method": "pypi-backfill-scan",
            },
            "owner_match": None,
        }},
        # A published:true PyPI product, to prove the check does not
        # false-positive on a legitimately-published package that also
        # mentions PyPI in its prose / links.
        "cells": {"python": {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-cells-foss"},
            "candidate_owner": "Aspose",
            "verification": {
                "published": True,
                "verified_at": "2026-08-01",
                "verified_owner": "Aspose",
                "evidence_url": "https://pypi.org/pypi/aspose-cells-foss/json",
                "method": "pypi-json-api",
            },
            "owner_match": None,
        }},
    }

    def test_barcode_python_pypi_prose_claim_is_fail(self, tmp_path):
        """Negative case: real barcode/python installation.md prose (adapted
        from the live file) asserts PyPI availability while
        verification.published is false -- must FAIL."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation of Aspose.BarCode FOSS for Python\n\n"
            "Aspose.BarCode FOSS for Python is distributed as a pure-Python "
            "package on PyPI. There are no native extensions to compile.\n\n"
            "The simplest way to install Aspose.BarCode FOSS is directly from PyPI:\n\n"
            "**CI/CD:** Add `pip install aspose-barcode-foss` to your CI pipeline's "
            "dependency step. No additional setup is required.\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "IR_PUBLISH_CLAIM"]
        assert len(fails) >= 1, f"expected FAIL for false PyPI claim, got: {findings}"
        assert any("PyPI" in f.message and "published=false" in f.message for f in fails)
        assert any("2026-08-01" in f.message for f in fails)

    def test_barcode_python_pypi_link_is_fail(self, tmp_path):
        """Negative case: a markdown link into pypi.org (license.md's real
        '[PyPI Page](https://pypi.org/project/aspose-barcode-foss/)') must
        also FAIL, not just prose mentions of the channel name."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: License\n---\n\n"
            "## Resources\n\n"
            "- [PyPI Page](https://pypi.org/project/aspose-barcode-foss/): Package page with full metadata\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/license.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "IR_PUBLISH_CLAIM"]
        assert len(fails) >= 1, f"expected FAIL for PyPI link claim, got: {findings}"

    def test_barcode_python_index_page_still_fails(self, tmp_path):
        """The false claim must be caught on _index.md too, even though the
        'missing install instructions' INFO suggestion explicitly skips
        _index.md pages -- RC-W1-003 must run unconditionally, same as
        _verify_install_accuracy, not gated behind the index-page skip."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Getting Started\n---\n\n"
            "## Getting Started\n\n"
            "Install from PyPI using pip:\n\n"
            "- **[Installation Guide](installation/)**: Virtual environment setup, pip install, and verification\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/_index.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "IR_PUBLISH_CLAIM"]
        assert len(fails) >= 1, f"expected FAIL on _index.md, got: {findings}"

    def test_published_true_pypi_mention_is_not_flagged(self, tmp_path):
        """Positive case: a legitimately-published PyPI product (cells/python,
        verification.published=true) must NOT be flagged just for mentioning
        PyPI or linking to its own real PyPI page -- proves no false positive."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "Aspose.Cells FOSS for Python is distributed as a pure-Python package on PyPI.\n\n"
            "- [PyPI Page](https://pypi.org/pypi/aspose-cells-foss/json): Package page with full metadata\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/cells/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "IR_PUBLISH_CLAIM"
                 and "published on PyPI" in f.message]
        assert fails == [], f"published:true product must not be flagged: {fails}"

    def test_unregistered_family_platform_not_flagged_by_channel_check(self, tmp_path):
        """A family/platform with no registry entry at all has nothing to
        contradict a claim with -- must not raise (separate from the
        existing UNREGISTERED-family FAIL for install commands)."""
        path = _write_page(
            tmp_path, "docs.aspose.org/en/unknown-family/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\nThis package is distributed on PyPI.\n",
        )
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        channel_fails = [f for f in findings if "published on PyPI" in f.message]
        assert channel_fails == []

    def test_honest_not_yet_published_prose_not_flagged(self, tmp_path):
        """A page that accurately says the package is NOT yet on PyPI must
        not be flagged as a contradiction -- it agrees with the registry."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "Aspose.BarCode FOSS for Python is not yet published on PyPI. Build from source instead.\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if "published on PyPI" in f.message]
        assert fails == [], f"honest not-yet-published prose must not be flagged: {fails}"

    def test_honest_not_yet_published_prose_wrapped_across_lines_not_flagged(self, tmp_path):
        """Regression: this repo's generated markdown hard-wraps prose, so a
        single logical sentence routinely splits the negation word ("not
        yet") onto the physical line BEFORE the channel-name mention (e.g.
        "...is not yet\npublished on PyPI:"). The negation guard must look
        one line back, not just the line containing the channel mention.
        Found live 2026-09-03, cells/rust's real launch blog posts (both
        wrapped "the crate is not yet\npublished on crates.io):" across
        exactly this line boundary)."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "Add the package to your project (it is not yet\n"
            "published on PyPI):\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if "published on PyPI" in f.message]
        assert fails == [], f"honest, line-wrapped not-yet-published prose must not be flagged: {fails}"


class TestNonEnglishChannelClaimsCrossCheckedAgainstEnglish:
    """ST-214 (2026-09-24): _NOT_PUBLISHED_NEGATION_RE is English-only prose
    (bare "not (yet) published"/"build from source" etc.), so a faithful
    non-English translation of an already-clean English sentence can trip
    IR_PUBLISH_CLAIM purely because the negation regex is script-blind, not
    because the translation says anything different. Real case: 3d/typescript's
    Arabic developer-guide/features.md, a faithful rendering of English's own
    accepted "...installed automatically by the npm install step used to
    build from source" sentence. Fix: for a non-English page, if its English
    counterpart is itself clean for this exact channel, trust the
    translation instead of scanning script-blind negation prose."""

    def test_translation_of_clean_english_source_not_flagged(self, tmp_path):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        eng_body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "Aspose.BarCode FOSS for Python has a single runtime dependency, "
            "fetched automatically by the pip install step used to build from source.\n"
        )
        # A faithful non-English rendering of the SAME sentence -- no literal
        # English negation phrase present, but also no real publish claim.
        ar_body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "يحتوي Aspose.BarCode FOSS for Python على تبعية تشغيل واحدة، "
            "يتم تثبيتها تلقائيًا بواسطة pip.\n"
        )
        _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", eng_body)
        ar_path = _write_page(tmp_path, "docs.aspose.org/ar/barcode/python/getting-started/installation.md", ar_body)
        page = Page.load(ar_path)
        assert page.locale == "ar"
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.category == "IR_PUBLISH_CLAIM"]
        assert fails == [], f"translation of a clean English source must not be flagged: {fails}"

    def test_translation_still_flagged_when_english_itself_has_the_claim(self, tmp_path):
        """Negative control: suppression must NOT fire just because a page
        is non-English -- only when the English counterpart is itself
        clean. Here English genuinely, wrongly claims PyPI availability, so
        its translation carrying the same (translated) claim must still FAIL."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        eng_body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "The simplest way to install is directly from PyPI using pip.\n"
        )
        ar_body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "أسهل طريقة للتثبيت هي مباشرة من PyPI باستخدام pip.\n"
        )
        _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", eng_body)
        ar_path = _write_page(tmp_path, "docs.aspose.org/ar/barcode/python/getting-started/installation.md", ar_body)
        page = Page.load(ar_path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.category == "IR_PUBLISH_CLAIM"]
        assert len(fails) >= 1, f"translation of a genuinely-wrong English claim must still FAIL: {findings}"

    def test_falls_back_to_normal_check_when_no_english_counterpart_exists(self, tmp_path):
        """No English file on disk at all -- must not crash, and must fall
        back to the page's own (English-regex) scan rather than silently
        suppressing everything."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        ar_body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "The simplest way to install is directly from PyPI using pip.\n"
        )
        ar_path = _write_page(tmp_path, "docs.aspose.org/ar/barcode/python/getting-started/installation.md", ar_body)
        page = Page.load(ar_path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.category == "IR_PUBLISH_CLAIM"]
        assert len(fails) >= 1, "with no English counterpart to trust, the normal scan must still apply"

    # Reuse the same registry fixture as the sibling class above.
    _BARCODE_PYTHON_REGISTRY = TestPublishChannelClaimsMatchVerificationPublished._BARCODE_PYTHON_REGISTRY


class TestNoUnpublishedDisclosureAllowed:
    """ST-054 TC-14/TC-16 (governing plan §Q.5): the opposite-direction check
    from TestPublishChannelClaimsMatchVerificationPublished above -- a page
    must never disclose non-publication status at all (explicit operator
    policy, 2026-09-03/2026-09-10), not just avoid falsely claiming
    publication. Shipped as WARN in TC-14, promoted to FAIL in TC-16 once
    all 46 pre-existing instances were remediated (commit f73e203027) --
    see _verify_no_unpublished_disclosure's own docstring."""

    _BARCODE_PYTHON_REGISTRY = TestPublishChannelClaimsMatchVerificationPublished._BARCODE_PYTHON_REGISTRY

    def test_is_not_yet_published_prose_is_fail(self, tmp_path):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "Aspose.BarCode FOSS for Python is not yet published on PyPI.\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and "discloses non-publication status" in f.message]
        assert len(fails) == 1, f"expected exactly 1 disclosure FAIL, got: {findings}"

    def test_coming_soon_prose_is_fail(self, tmp_path):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "PyPI support is coming soon for this library.\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and "discloses non-publication status" in f.message]
        assert len(fails) == 1

    def test_build_from_source_prose_never_misfires(self, tmp_path):
        """The narrow new regex must never trigger on legitimate build-from-
        source guidance -- that's now the CORRECT answer a page should give
        (ST-054 TC-13's shortcode fix renders exactly this), on either a
        published or unpublished product."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "git clone https://github.com/aspose-barcode-foss/example.git\n"
            "cd example\n"
            "pip install -e .\n\n"
            "You can also build from source for the latest development version.\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        disclosure_warns = [f for f in findings if "discloses non-publication status" in f.message]
        assert disclosure_warns == [], f"legitimate build-from-source prose must never misfire: {disclosure_warns}"

    def test_published_true_product_never_flagged_even_with_disclosure_phrase(self, tmp_path):
        """This check only applies to confirmed-unpublished entries -- a
        published:true product mentioning e.g. 'coming soon' for an
        unrelated feature must not be flagged."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=self._BARCODE_PYTHON_REGISTRY)
        body = (
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n"
            "Aspose.Cells FOSS for Python is available on PyPI today. A native "
            "extension build is coming soon as a future performance improvement.\n"
        )
        path = _write_page(tmp_path, "docs.aspose.org/en/cells/python/getting-started/installation.md", body)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        disclosure_warns = [f for f in findings if "discloses non-publication status" in f.message]
        assert disclosure_warns == []

    def test_unregistered_family_platform_not_flagged(self, tmp_path):
        path = _write_page(
            tmp_path, "docs.aspose.org/en/unknown-family/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\nThis package is not yet published anywhere.\n",
        )
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        disclosure_warns = [f for f in findings if "discloses non-publication status" in f.message]
        assert disclosure_warns == []


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
