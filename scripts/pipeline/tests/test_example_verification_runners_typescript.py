"""Tests for lib/example_verification/runners/typescript.py (rollout step
C3): a faithful port of S-120's real TypeScript verification runner
(readme_refresh_run.py:5144-5426). Real, network-independent logic is
exercised for real; the network-dependent half (a real `npm install`) is
deliberately NOT re-exercised here, matching this repo's own established
test convention for the original functions (their own test file's
comments say the same).

Includes direct parity checks against the real, unmodified S-120 functions
(imported as `rr`) for identical inputs.
"""
from __future__ import annotations

from pathlib import Path

import readme_refresh_run as rr

from lib.example_verification.runners.typescript import (
    acquire_typescript_environment,
    classify_typescript_failure,
    self_link_typescript_package,
    typescript_block_starts_chain,
    typescript_verification_runner,
)


# --- Direct behavior (mirrors test_readme_refresh_run.py's own test names/shapes) --------------

def test_acquire_typescript_environment_no_clone_cache(tmp_path):
    result = acquire_typescript_environment(tmp_path, tmp_path / "no-such-clone-cache")
    assert result["ok"] is False
    assert "no clone cache directory" in result["detail"]


def test_acquire_typescript_environment_no_package_json(tmp_path):
    clone_cache = tmp_path / "clone_cache"
    clone_cache.mkdir()
    (clone_cache / "README.md").write_text("# hi\n", encoding="utf-8")
    result = acquire_typescript_environment(tmp_path, clone_cache)
    assert result["ok"] is False
    assert "no package.json" in result["detail"]


def test_self_link_typescript_package_creates_a_real_symlink_back_to_the_project(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "dist").mkdir()
    (project_dir / "dist" / "index.js").write_text("export const x = 1;\n", encoding="utf-8")

    try:
        created = self_link_typescript_package(project_dir, "@asposefoss/pdf")
    except OSError:
        import pytest
        pytest.skip("symlinks not permitted in this environment")

    assert created is True
    link = project_dir / "node_modules" / "@asposefoss" / "pdf"
    assert link.is_symlink()
    assert (link / "dist" / "index.js").read_text(encoding="utf-8") == "export const x = 1;\n"


def test_self_link_typescript_package_handles_an_unscoped_name(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    created = self_link_typescript_package(project_dir, "plain-package-name")
    if created:
        assert (project_dir / "node_modules" / "plain-package-name").is_symlink()


def test_self_link_typescript_package_is_a_noop_without_a_declared_name(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    assert self_link_typescript_package(project_dir, None) is False
    assert not (project_dir / "node_modules").exists()


def test_typescript_verification_runner_non_typescript_blocks_stay_stub(tmp_path):
    candidate_path = tmp_path / "readme.md"
    candidate_path.write_text(
        "## Installation\n\n```bash\nnpm install\n```\n\n"
        "## Quick Start\n\n```csharp\nvar x = 1;\n```\n",
        encoding="utf-8",
    )
    result = typescript_verification_runner(candidate_path, {"family": "testfam", "platform": "testplat"})
    assert result["runner"] == "typescript_verification_runner_v2"
    assert result["blocks_found"] == 2
    assert result["all_named"] is True
    assert all(b["status"] == "BLOCKED-WITH-REASON" and b["reason"] == "TOOLCHAIN-UNAVAILABLE"
               for b in result["block_statuses"])


def test_typescript_verification_runner_recognizes_both_typescript_and_ts_tags(tmp_path):
    candidate_path = tmp_path / "readme.md"
    candidate_path.write_text(
        "## A\n\n```typescript\nconsole.log(1);\n```\n\n## B\n\n```ts\nconsole.log(2);\n```\n",
        encoding="utf-8",
    )
    result = typescript_verification_runner(candidate_path, {"family": "nope", "platform": "nope"})
    assert result["blocks_found"] == 2
    assert all(b["reason"] == "ACQUIRE-FAILED" for b in result["block_statuses"])


def test_typescript_block_starts_chain_on_a_leading_import():
    assert typescript_block_starts_chain("import { Document } from '@asposefoss/pdf';\nconst x = 1;\n") is True


def test_typescript_block_starts_chain_false_for_a_continuation_fragment():
    assert typescript_block_starts_chain("const doc = Document.OpenFile('in.pdf');\ndoc.WriteTo('out.pdf');\n") is False


def test_typescript_block_starts_chain_skips_leading_blank_lines_and_line_comments():
    code = "\n// a leading comment\n\nimport { Document } from '@asposefoss/pdf';\n"
    assert typescript_block_starts_chain(code) is True
    code2 = "\n// a leading comment\n\ndoc.Save();\n"
    assert typescript_block_starts_chain(code2) is False


def test_typescript_block_starts_chain_empty_code_defaults_true():
    assert typescript_block_starts_chain("") is True
    assert typescript_block_starts_chain("   \n  \n") is True


def test_classify_typescript_failure_names_a_missing_upstream_export_as_upstream_broken():
    output = (
        "SyntaxError: The requested module '@asposefoss/pdf' does not provide an export "
        "named 'htmlFileToPdf'\n    at ModuleJob.run (...)"
    )
    reason, detail = classify_typescript_failure(output)
    assert reason == "UPSTREAM-BROKEN"
    assert "htmlFileToPdf" in detail


def test_classify_typescript_failure_stays_runtime_error_for_an_ordinary_reference_error():
    reason, _detail = classify_typescript_failure("ReferenceError: doc is not defined")
    assert reason == "RUNTIME-ERROR"


# --- Parity against the real, unmodified S-120 functions --------------------------------------

def test_acquire_typescript_environment_parity_no_clone_cache(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ours = acquire_typescript_environment(tmp_path / "a", tmp_path / "no-clone-a")
    theirs = rr._acquire_typescript_environment(tmp_path / "b", tmp_path / "no-clone-b")
    assert ours == theirs


def test_acquire_typescript_environment_parity_no_package_json(tmp_path):
    clone_a = tmp_path / "clone_a"
    clone_a.mkdir()
    (clone_a / "README.md").write_text("# hi\n", encoding="utf-8")
    clone_b = tmp_path / "clone_b"
    clone_b.mkdir()
    (clone_b / "README.md").write_text("# hi\n", encoding="utf-8")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ours = acquire_typescript_environment(tmp_path / "a", clone_a)
    theirs = rr._acquire_typescript_environment(tmp_path / "b", clone_b)
    assert ours == theirs


def test_typescript_block_starts_chain_parity_with_s120():
    cases = [
        "import { Document } from '@asposefoss/pdf';\nconst x = 1;\n",
        "const doc = Document.OpenFile('in.pdf');\ndoc.WriteTo('out.pdf');\n",
        "\n// leading comment\n\nimport { X } from 'y';\n",
        "", "   \n  \n",
    ]
    for code in cases:
        assert typescript_block_starts_chain(code) == rr._typescript_block_starts_chain(code)


def test_classify_typescript_failure_parity_with_s120():
    cases = [
        "SyntaxError: The requested module '@asposefoss/pdf' does not provide an export named 'foo'",
        "ReferenceError: doc is not defined",
        "TypeError: Cannot read properties of undefined",
    ]
    for output in cases:
        assert classify_typescript_failure(output) == rr._classify_typescript_failure(output)


def test_self_link_typescript_package_parity_noop_case(tmp_path):
    project_a = tmp_path / "a"
    project_a.mkdir()
    project_b = tmp_path / "b"
    project_b.mkdir()
    ours = self_link_typescript_package(project_a, None)
    theirs = rr._self_link_typescript_package(project_b, None)
    assert ours == theirs is False


def test_typescript_verification_runner_parity_with_s120_stub_case(tmp_path):
    candidate = tmp_path / "candidate.md"
    candidate.write_text(
        "```csharp\nvar x = 1;\n```\n\n```java\nSystem.out.println(1);\n```\n",
        encoding="utf-8",
    )
    ours = typescript_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    theirs = rr.typescript_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    assert ours == theirs


def test_typescript_verification_runner_byte_identical_rerun(tmp_path):
    candidate = tmp_path / "candidate.md"
    candidate.write_text("```csharp\nvar x = 1;\n```\n", encoding="utf-8")
    r1 = typescript_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    r2 = typescript_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    assert r1 == r2
