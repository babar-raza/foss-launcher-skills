"""Tests for smoke_test.py's fix in rollout step C2: the loader now
delegates to lib/example_verification/syntax.py (RC17 -- this used to be an
independent copy that disagreed with content_eval's own loader on which
languages got a tree_sitter_language_pack fallback), and a genuinely
missing grammar now reports a loud WARN instead of silently PASSing
(smoke_test.py:424-434, pre-fix).

Deliberately a separate file from tests/test_smoke_test.py (which is
outside this taskcard's allowed_paths) -- exercises smoke_test.py only
through its public check_file() API.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import smoke_test as smoke_test_mod
from smoke_test import check_file


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    smoke_test_mod.configure()


def _write_md(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "page.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_missing_grammar_is_a_loud_warn_not_a_silent_pass(tmp_path):
    # "cobol" is not a language lib.example_verification.syntax knows about
    # -- parser_for() returns None, standing in for a genuinely unavailable
    # grammar (the same code path a real missing grammar takes).
    md = _write_md(tmp_path, "```cobol\nIDENTIFICATION DIVISION.\n```\n")
    result = check_file(md, langs=frozenset({"cobol"}))
    assert result.warn_count == 1
    assert result.pass_count == 0
    assert result.fail_count == 0
    assert "GRAMMAR-UNAVAILABLE" in result.results[0].message
    assert result.results[0].status == "WARN"


def test_java_still_passes_through_shared_loader(tmp_path):
    md = _write_md(tmp_path, "```java\npublic class Foo {\n    void bar() {}\n}\n```\n")
    result = check_file(md, langs=frozenset({"java"}))
    assert result.pass_count == 1
    assert result.warn_count == 0
    assert result.fail_count == 0


def test_java_syntax_error_still_fails_through_shared_loader(tmp_path):
    md = _write_md(tmp_path, "```java\npublic class Foo {\n    void bar( {\n```\n")
    result = check_file(md, langs=frozenset({"java"}))
    assert result.fail_count == 1


# ---------------------------------------------------------------------------
# TC-03 (MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION): real
# tier-3 dispatch through lib/example_verification/api.py.
# ---------------------------------------------------------------------------

def test_tier_below_3_never_calls_the_shared_api(tmp_path):
    """tier<=2 must stay on the original py_compile/tree-sitter path --
    dispatching through the api would be a behavior change this taskcard
    deliberately avoids for the proven, already-tested tiers."""
    def _boom(*a, **k):
        raise AssertionError("verify_page must not be called for max_tier<3")

    smoke_test_mod.configure(verify_page_fn=_boom)
    md = _write_md(tmp_path, "```python\nprint('hi')\n```\n")
    result = check_file(md, langs=frozenset({"python"}), max_tier=2, family="pdf", platform="python")
    assert result.pass_count == 1


def test_tier_3_without_family_and_platform_does_not_dispatch(tmp_path):
    """check_file() itself only dispatches tier 3 when BOTH family and
    platform are given (main()'s own fallback-to-2 warning covers the
    CLI path; this proves the underlying function is equally safe when
    called directly with tier=3 but no product context)."""
    def _boom(*a, **k):
        raise AssertionError("verify_page must not be called without family+platform")

    smoke_test_mod.configure(verify_page_fn=_boom)
    md = _write_md(tmp_path, "```python\nprint('hi')\n```\n")
    result = check_file(md, langs=frozenset({"python"}), max_tier=3)
    assert result.pass_count == 1  # fell through to the tier<=2 path


def test_tier_3_dispatches_through_the_shared_api_and_adapts_to_smoke_shape(tmp_path):
    """The core TC-03 contract: max_tier=3 + family + platform calls
    api.verify_page() once and adapts VerificationReport.to_smoke() into
    this module's own SmokeResult/BlockResult shape, 1-based block_index."""
    from example_verification.result import BlockIdentity, BlockResult as EvBlockResult, VerificationReport

    md = _write_md(tmp_path, "```python\nprint('hi')\n```\n")
    fake_report = VerificationReport(
        runner="python",
        blocks=[EvBlockResult(
            identity=BlockIdentity(code_sha256="x", lang="python", index=0, start_line=1, end_line=2),
            status="PASS", proof_tier=3,
        )],
    )

    captured = {}

    def fake_verify_page(path, *, family, platform, policy):
        captured["path"] = path
        captured["family"] = family
        captured["platform"] = platform
        captured["max_tier"] = policy.max_tier
        captured["allow_acquire"] = policy.allow_acquire
        return fake_report

    smoke_test_mod.configure(verify_page_fn=fake_verify_page)

    result = check_file(md, langs=frozenset({"python"}), max_tier=3, family="pdf", platform="python")

    assert captured["path"] == md
    assert captured["family"] == "pdf"
    assert captured["platform"] == "python"
    assert captured["max_tier"] == 3
    assert captured["allow_acquire"] is True
    assert result.blocks_checked == 1
    assert result.pass_count == 1
    assert result.results[0].block_index == 1  # 0-based identity.index + 1
    assert result.results[0].status == "PASS"


def test_tier_3_blocked_block_maps_to_fail_status(tmp_path):
    from example_verification.result import BlockIdentity, BlockResult as EvBlockResult, VerificationReport

    md = _write_md(tmp_path, "```go\npackage main\nfunc main( {\n```\n")
    fake_report = VerificationReport(
        runner="go",
        blocks=[EvBlockResult(
            identity=BlockIdentity(code_sha256="x", lang="go", index=0, start_line=1, end_line=3),
            status="BLOCKED-WITH-REASON", reason="SYNTAX-ERROR", detail="syntax error at line 2",
            proof_tier=1,
        )],
    )
    smoke_test_mod.configure(verify_page_fn=lambda *a, **k: fake_report)

    result = check_file(md, langs=frozenset({"go"}), max_tier=3, family="pdf", platform="go")
    assert result.fail_count == 1
    assert result.results[0].status == "FAIL"
    assert "syntax error at line 2" in result.results[0].message


def test_tier_3_dispatch_exception_isolated_as_warn_not_propagated(tmp_path):
    """Independent-review fast-follow: an unexpected exception from the
    real dispatch (acquire crash, timeout escaping its own runner, etc.)
    must never propagate out of check_file() -- that would kill an
    entire multi-file check_product() scan over one bad page."""
    def _raise(*a, **k):
        raise RuntimeError("simulated acquire crash")

    smoke_test_mod.configure(verify_page_fn=_raise)
    md = _write_md(tmp_path, "```go\npackage main\nfunc main() {}\n```\n")
    result = check_file(md, langs=frozenset({"go"}), max_tier=3, family="pdf", platform="go")

    assert result.fail_count == 0
    assert result.warn_count == 1
    assert "VERIFICATION-ERROR" in result.results[0].message
    assert "RuntimeError" in result.results[0].message


def test_tier_3_block_index_is_sequential_regardless_of_underlying_identity_index(tmp_path):
    """Independent-review fast-follow: python/typescript's whole-candidate
    identity.index counts EVERY fence in the file (any language), while
    go/net/java/rust/cpp's BaseRunner path counts only same-language
    fences -- the old `+1` scheme leaked that difference into
    block_index. Enumerating to_smoke()'s own result order must always
    give a clean 1..N sequence."""
    from example_verification.result import BlockIdentity, BlockResult as EvBlockResult, VerificationReport

    md = _write_md(tmp_path, "```bash\npip install foo\n```\n\n```python\nprint('hi')\n```\n")
    # Simulates the real whole-candidate shape: bash is whole-file index 0,
    # python is whole-file index 5 (as if several other fences preceded it
    # in a bigger real file) -- block_index must still come out as 1, 2.
    fake_report = VerificationReport(
        runner="python",
        blocks=[
            EvBlockResult(
                identity=BlockIdentity(code_sha256="a", lang="bash", index=0, start_line=1, end_line=3),
                status="BLOCKED-WITH-REASON", reason="TOOLCHAIN-UNAVAILABLE", proof_tier=0,
            ),
            EvBlockResult(
                identity=BlockIdentity(code_sha256="b", lang="python", index=5, start_line=5, end_line=7),
                status="PASS", proof_tier=3,
            ),
        ],
    )
    smoke_test_mod.configure(verify_page_fn=lambda *a, **k: fake_report)

    result = check_file(md, langs=frozenset({"python"}), max_tier=3, family="pdf", platform="python")
    indices = [b.block_index for b in result.results]
    assert indices == sorted(indices) == list(range(1, len(indices) + 1))
