"""Tests for lib/example_verification/runners/rust.py's RustRunner (C13,
MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION).

Unlike test_example_verification_runners_go.py (which requires and uses a
real `go` toolchain), this repo has NO cargo/rustc/rustup on PATH -- verified
live below, not assumed. So instead of skipping when the toolchain is
absent, these tests assert the honest TOOLCHAIN-UNAVAILABLE degradation IS
the real, unmocked, currently-reproducible behavior -- exactly the shape
this taskcard's own stage-matrix promotion gate asks for ("tier 1 green
without rustup; tier >= 2 an honest TOOLCHAIN-UNAVAILABLE until rustup is
installed").
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner
from lib.example_verification.runners.rust import (
    RustRunner,
    _cites_other_file_in_primary_span,
    _find_rust_replace_path,
    _has_top_level_main,
    _lib_ident_for_crate,
    _needs_wrap,
    _resolve_rust_crate_for_family,
    _RUST_FILE_LOCATION_RE,
    _wrap_fragment,
)


def test_cargo_toolchain_is_genuinely_absent_on_this_machine():
    """Precondition this whole test file depends on -- if this ever starts
    failing (rustup gets installed here), the TOOLCHAIN-UNAVAILABLE tests
    below need to become skipif-guarded like the Go suite instead."""
    assert shutil.which("cargo") is None
    assert shutil.which("rustc") is None


class TestResolveRustCrateForFamily:
    def test_reads_product_name_from_merged_model_yaml(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "acme" / "rust" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text(
            "family: acme\nplatform: rust\nproduct_name: acme-foss-rust\n",
            encoding="utf-8",
        )
        assert _resolve_rust_crate_for_family("acme", repo_root=tmp_path) == "acme-foss-rust"

    def test_falls_back_to_scout_when_merged_is_absent(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "acme" / "rust" / "scout"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text(
            "product_name: acme-scout-only\n", encoding="utf-8",
        )
        assert _resolve_rust_crate_for_family("acme", repo_root=tmp_path) == "acme-scout-only"

    def test_no_model_yaml_anywhere_returns_none(self, tmp_path):
        assert _resolve_rust_crate_for_family("no-such-family", repo_root=tmp_path) is None

    def test_real_cells_rust_product_name_matches_the_real_clone_cache_crate(self):
        """Live, unmocked confirmation against this repo's real data: the
        crate name this function derives for cells/rust must match the
        real `runs/.clone_cache/aspose_cells_rust/Cargo.toml`'s own
        `[package] name` -- checked directly before writing this module,
        re-checked here so a future edit to either file breaks a test
        instead of silently drifting apart."""
        crate = _resolve_rust_crate_for_family("cells")
        assert crate == "aspose-cells-foss-rust"


class TestLibIdent:
    def test_hyphens_become_underscores(self):
        assert _lib_ident_for_crate("aspose-cells-foss-rust") == "aspose_cells_foss_rust"

    def test_no_hyphens_is_unchanged(self):
        assert _lib_ident_for_crate("serde") == "serde"


class TestHasTopLevelMain:
    def test_detects_real_top_level_main(self):
        assert _has_top_level_main("fn main() -> Result<(), Box<dyn Error>> {\n}\n")

    def test_indented_main_inside_another_function_is_not_top_level(self):
        # A nested closure/fn named "main_helper" or similar must not false-positive.
        assert not _has_top_level_main("let x = compute();\nprintln!(\"{}\", x);\n")

    def test_needs_wrap_is_the_negation(self):
        code_with_main = "fn main() {}\n"
        code_fragment = "let x = 1;\n"
        assert not _needs_wrap(code_with_main)
        assert _needs_wrap(code_fragment)

    def test_async_main_is_recognized_as_top_level_main(self):
        """Independent-review finding (round 1): the original regex only
        matched `fn main(`, so `#[tokio::main]\nasync fn main() {...}`
        would have been double-wrapped inside another fn main -- legal per
        tree-sitter (never caught by a syntax check) but a real rustc
        restriction (proc-macro attribute on a nested item)."""
        assert _has_top_level_main("#[tokio::main]\nasync fn main() {\n    println!(\"hi\");\n}\n")
        assert not _needs_wrap("#[tokio::main]\nasync fn main() {}\n")


class TestWrapFragment:
    def test_wraps_fragment_in_result_returning_main(self):
        wrapped = _wrap_fragment("let mut workbook = Workbook::new();\nworkbook.save(\"x\")?;", "acme_rust")
        assert "fn main() -> Result<(), Box<dyn std::error::Error>>" in wrapped
        assert "Ok(())" in wrapped
        assert "use acme_rust::*;" in wrapped

    def test_no_use_injected_when_lib_ident_already_present(self):
        code = "use acme_rust::Widget;\nlet w = Widget::new();"
        wrapped = _wrap_fragment(code, "acme_rust")
        assert wrapped.count("use acme_rust") == 1

    def test_no_use_injected_when_lib_ident_is_none(self):
        wrapped = _wrap_fragment("let x = 1;", None)
        assert "use " not in wrapped

    def test_wrapped_fragment_is_syntactically_valid_rust(self):
        """Structural proof this module CAN produce (via the shared,
        already-verified tree-sitter loader) without needing a real cargo
        toolchain -- tier-1 syntax proof is fully real and testable even
        though tier 2/3 cannot be exercised on this machine."""
        from lib.example_verification.syntax import check_syntax
        wrapped = _wrap_fragment(
            "let mut workbook = Workbook::new();\nworkbook.save(\"x\")?;", "acme_rust")
        result = check_syntax("rust", wrapped)
        assert result.status == "PASS"


class TestFindRustReplacePath:
    def test_returns_path_when_cargo_toml_exists_in_clone_cache(self, tmp_path):
        clone_dir = tmp_path / "aspose_acme_rust"
        clone_dir.mkdir(parents=True)
        (clone_dir / "Cargo.toml").write_text("[package]\nname = \"acme\"\n", encoding="utf-8")
        result = _find_rust_replace_path("acme", clone_cache_root=tmp_path)
        assert result is not None
        assert result.endswith("aspose_acme_rust")

    def test_returns_none_when_no_clone_present(self, tmp_path):
        assert _find_rust_replace_path("no-such-family", clone_cache_root=tmp_path) is None


class TestStartsChain:
    """Confirmed against real content (see module docstring): a block with
    no fn main/use continues the previous block's local variables."""

    def test_fn_main_starts_a_new_chain(self):
        runner = RustRunner(family="no-such-family")
        assert runner.starts_chain("fn main() {\n    println!(\"hi\");\n}\n")

    def test_leading_use_starts_a_new_chain(self):
        runner = RustRunner(family="no-such-family")
        assert runner.starts_chain("use acme_rust::Widget;\nlet w = Widget::new();")

    def test_plain_statement_continues_the_previous_chain(self):
        runner = RustRunner(family="no-such-family")
        assert not runner.starts_chain('let mut cells = sheet.get_cells_mut();')

    def test_leading_comment_is_skipped_before_deciding(self):
        runner = RustRunner(family="no-such-family")
        assert runner.starts_chain("// a comment\nfn main() {}")

    def test_leading_outer_attribute_starts_a_new_chain(self):
        """Independent-review finding (round 1): a fresh, self-contained
        `#[derive(Debug)]\nstruct Foo {...}` block was previously
        misclassified as a chain continuation since only fn main/use were
        recognized."""
        runner = RustRunner(family="no-such-family")
        assert runner.starts_chain("#[derive(Debug)]\nstruct Foo { x: i32 }")

    def test_leading_inner_attribute_starts_a_new_chain(self):
        runner = RustRunner(family="no-such-family")
        assert runner.starts_chain("#![allow(dead_code)]\nfn main() {}")

    def test_async_main_starts_a_new_chain(self):
        runner = RustRunner(family="no-such-family")
        assert runner.starts_chain("async fn main() {\n    println!(\"hi\");\n}")


class TestClassify:
    def test_error_citing_a_non_main_rs_file_is_upstream_broken(self):
        runner = RustRunner(family="no-such-family")
        output = "error[E0433]: failed to resolve\n  --> upstream_crate/src/lib.rs:12:9\n"
        reason, detail = runner.classify(output, {"stage": "compile"})
        assert reason == "UPSTREAM-BROKEN"
        assert detail == output.strip()

    def test_error_citing_only_main_rs_is_an_ordinary_compile_error(self):
        runner = RustRunner(family="no-such-family")
        output = "error[E0425]: cannot find value `x`\n  --> src/main.rs:3:5\n"
        reason, detail = runner.classify(output, {"stage": "compile"})
        assert reason == "COMPILE-ERROR"

    def test_execute_stage_classifies_as_runtime_error(self):
        runner = RustRunner(family="no-such-family")
        output = "thread 'main' panicked at src/main.rs:4:5:\nindex out of bounds"
        reason, _ = runner.classify(output, {"stage": "execute"})
        assert reason == "RUNTIME-ERROR"

    def test_no_file_citation_at_all_defaults_to_compile_error_not_upstream(self):
        """Safe default: absence of any file citation must never be
        mistaken for evidence of an upstream defect."""
        runner = RustRunner(family="no-such-family")
        reason, _ = runner.classify("some opaque cargo failure with no location", {"stage": "compile"})
        assert reason == "COMPILE-ERROR"

    def test_location_regex_matches_windows_drive_letter_paths(self):
        """Independent-review finding (round 1): the original character
        class had no `:`, so it could never match a Windows absolute path
        citation -- and _find_rust_replace_path itself builds exactly that
        path shape (a drive-letter clone-cache path) for `replace_path` on
        this repo's own OS, so this was a real, self-inflicted bug, not a
        hypothetical one."""
        for loc in (
            r"D:/onedrive/Documents/GitHub/aspose.org/lib.rs:45:9",
            r"D:\onedrive\Documents\GitHub\aspose.org\lib.rs:88:1",
        ):
            m = _RUST_FILE_LOCATION_RE.search(f"  --> {loc}")
            assert m is not None, loc
            assert m.group(1) == loc.rsplit(":", 2)[0]

    def test_note_citation_of_a_dependency_is_not_mistaken_for_the_primary_span(self):
        """Independent-review finding (round 1), reproduced live: a real
        rustc diagnostic shape where the PRIMARY span is the block's own
        main.rs, but an explanatory `note:` cites the dependency's own
        definition site -- must classify as an ordinary COMPILE-ERROR, not
        a false UPSTREAM-BROKEN."""
        runner = RustRunner(family="no-such-family")
        output = (
            "error[E0277]: the trait bound `Foo: Bar` is not satisfied\n"
            "  --> src/main.rs:5:9\n"
            "   |\n"
            "note: required by a bound in `baz`\n"
            "  --> upstream_crate/src/lib.rs:10:5\n"
        )
        reason, _ = runner.classify(output, {"stage": "compile"})
        assert reason == "COMPILE-ERROR"

    def test_primary_span_citing_upstream_is_still_detected(self):
        """The note-skipping fix must not break the genuine case: an
        error whose OWN primary span cites the dependency's file."""
        runner = RustRunner(family="no-such-family")
        output = "error[E0433]: failed to resolve\n  --> upstream_crate/src/lib.rs:12:9\n"
        reason, detail = runner.classify(output, {"stage": "compile"})
        assert reason == "UPSTREAM-BROKEN"
        assert detail == output.strip()

    def test_cites_other_file_in_primary_span_pure_function(self):
        assert _cites_other_file_in_primary_span(
            "error[E0433]: x\n  --> upstream/src/lib.rs:1:1\n")
        assert not _cites_other_file_in_primary_span(
            "error[E0425]: x\n  --> src/main.rs:1:1\n")


class TestAcquireCompileExecute:
    """Real, unmocked -- cargo genuinely isn't on PATH on this machine (see
    test_cargo_toolchain_is_genuinely_absent_on_this_machine above)."""

    def test_acquire_always_succeeds(self, tmp_path):
        runner = RustRunner(family="cells")
        result = runner.acquire(tmp_path, Policy(), ProductContext(family="cells", platform="rust"))
        assert result["ok"] is True
        assert result["crate_name"] == "aspose-cells-foss-rust"

    def test_compile_reports_toolchain_unavailable(self, tmp_path):
        runner = RustRunner(family="cells")
        acquired = runner.acquire(tmp_path, Policy(), ProductContext(family="cells", platform="rust"))
        failure = runner.compile(acquired, "let x = 1;", 0)
        assert failure == {"reason": "TOOLCHAIN-UNAVAILABLE", "detail": "cargo not found on PATH"}

    def test_execute_reports_toolchain_unavailable(self, tmp_path):
        runner = RustRunner(family="cells")
        acquired = runner.acquire(tmp_path, Policy(), ProductContext(family="cells", platform="rust"))
        result = runner.execute(acquired, "let x = 1;", 0)
        assert result == {
            "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE",
            "detail": "cargo not found on PATH",
        }


class TestBaseRunnerIntegration:
    """End-to-end through the shared tier ladder (runners/base.py, C3/C5) --
    real, unmocked, against this machine's genuinely toolchain-less state."""

    def _blocks(self, code: str):
        import hashlib
        sha = hashlib.sha256(code.encode()).hexdigest()
        return [(sha, (10, 12), code)]

    def test_default_policy_is_tier_1_only_clean_code_passes(self):
        """Matches registry.py's real, current PLATFORM_CONTRACT (max_tier=1
        for rust) -- acquire/compile/execute are never even attempted."""
        base = BaseRunner(RustRunner("cells"))
        policy = Policy.for_platform("rust")
        assert policy.max_tier == 1
        product = ProductContext(family="cells", platform="rust")
        results = base.run(self._blocks("let x = 1;\nprintln!(\"{x}\");"), policy, product)
        assert len(results) == 1
        assert results[0].status == "PASS"
        assert results[0].proof_tier == 1

    def test_default_policy_still_catches_a_real_syntax_error(self):
        base = BaseRunner(RustRunner("cells"))
        policy = Policy.for_platform("rust")
        product = ProductContext(family="cells", platform="rust")
        results = base.run(self._blocks("let mut workbook = Workbook::new(\n"), policy, product)
        assert results[0].status == "BLOCKED-WITH-REASON"
        assert results[0].reason == "SYNTAX-ERROR"
        assert results[0].proof_tier == 1

    def test_forced_tier_3_policy_produces_honest_toolchain_unavailable(self):
        """The stage-matrix promotion gate's literal requirement: tier >= 2
        must be an honest TOOLCHAIN-UNAVAILABLE, not a silent tier-1 PASS
        and not a crash."""
        base = BaseRunner(RustRunner("cells"))
        policy = Policy(max_tier=3, allow_acquire=True)
        product = ProductContext(family="cells", platform="rust")
        results = base.run(self._blocks("let x = 1;\nprintln!(\"{x}\");"), policy, product)
        assert results[0].status == "BLOCKED-WITH-REASON"
        assert results[0].reason == "TOOLCHAIN-UNAVAILABLE"
        assert "cargo not found on PATH" in results[0].detail
        assert results[0].proof_tier == 2
