"""Tests for redact_plan_state_paths.py (TC-GOV-01-02,
MT071-2026-09-17-GOVERNANCE-DURABILITY-HARDENING).

Written TDD-first, before the implementation module exists. Fixtures mirror
the real embedded-path shapes confirmed live in this repo's own
reports/plan_state/** (2026-09-18): a raw single-backslash Windows path in
YAML (`C:\\Users\\prora\\...`), a forward-slash Windows path in YAML
(`C:/Users/prora/...` -- also observed live), a JSON-string-escaped
double-backslash Windows path inside a .jsonl `source_finding` field, plus
synthetic Unix/macOS shapes the tool must also cover per the taskcard's own
spec ("/home/<user>/...", "or similar").

Mirrors install_change_budget.py's own test-file shape (module-level
`configure()` reset via an autouse fixture) and its DI-over-monkeypatch
testing convention (test_install_change_budget.py).
"""
from __future__ import annotations

import pytest

import redact_plan_state_paths as rpsp


@pytest.fixture(autouse=True)
def _reset_module_state():
    yield
    rpsp.configure()


def _write(path, text, newline=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


def _read_raw(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Detection -- find_matches_in_text / scan_file
# ---------------------------------------------------------------------------

def test_finds_windows_backslash_path_in_yaml(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "concurrent-toasting-biscuit" / "mission_authority.yaml"
    _write(f, "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\concurrent-toasting-biscuit.md\n")

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "C:\\Users\\prora\\.claude\\plans\\concurrent-toasting-biscuit.md"
    assert findings[0].placeholder == "<local-plan-cache>/concurrent-toasting-biscuit.md"


def test_finds_windows_forward_slash_path_in_yaml(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-x" / "mission_authority.yaml"
    _write(f, "governing_plan_path: C:/Users/prora/.claude/plans/this-chat-is-about-polymorphic-brook.md\n")

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "C:/Users/prora/.claude/plans/this-chat-is-about-polymorphic-brook.md"
    assert findings[0].placeholder == "<local-plan-cache>/this-chat-is-about-polymorphic-brook.md"


def test_finds_json_escaped_windows_path_in_jsonl(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH" / "taskcards.jsonl"
    _write(
        f,
        '{"task_id": "TC-01", "source_finding": '
        '"C:\\\\Users\\\\prora\\\\.claude\\\\plans\\\\pdf-typescript-foo.md Phase A"}\n',
    )

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "C:\\\\Users\\\\prora\\\\.claude\\\\plans\\\\pdf-typescript-foo.md"
    assert findings[0].placeholder == "<local-plan-cache>/pdf-typescript-foo.md"


def test_finds_unix_home_path(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-y" / "mission_authority.yaml"
    _write(f, "governing_plan_path: /home/alice/.claude/plans/foo.md\n")

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "/home/alice/.claude/plans/foo.md"
    assert findings[0].placeholder == "<local-plan-cache>/foo.md"


def test_finds_macos_users_path(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-z" / "mission_authority.yaml"
    _write(f, "governing_plan_path: /Users/bob/.claude/plans/bar.md\n")

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "/Users/bob/.claude/plans/bar.md"
    assert findings[0].placeholder == "<local-plan-cache>/bar.md"


def test_finds_msys_drive_letter_windows_path(tmp_path):
    """TC-GOV-01-04: a 5th real leak shape found live during full-tree recon
    (reports/plan_state/MT014-.../independent-verification-20260731.md) --
    Git-Bash/MSYS renders a Windows drive letter as a single-letter leading
    path segment instead of '<letter>:', e.g. '/c/Users/prora/...' is the
    exact same leak as 'C:\\Users\\prora\\...', just captured verbatim from a
    shell command's own output."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-msys" / "notes.md"
    _write(f, "/c/Users/prora/AppData/Local/Microsoft/WinGet/Packages/hugo.exe\n")

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "/c/Users/prora/AppData/Local/Microsoft/WinGet/Packages/hugo.exe"
    assert findings[0].placeholder == "<local-plan-cache>/hugo.exe"


def test_finds_msys_drive_letter_home_path(tmp_path):
    """Same MSYS convention, /home/ variant (a different drive letter)."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-msys2" / "notes.md"
    _write(f, "See /d/home/alice/.claude/plans/foo.md for details.\n")

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "/d/home/alice/.claude/plans/foo.md"
    assert findings[0].placeholder == "<local-plan-cache>/foo.md"


def test_does_not_match_home_as_a_family_name_with_msys_pattern_active(tmp_path):
    """Regression guard: adding the MSYS drive-letter pattern must not
    reopen the already-fixed 'cells/home/html' family-list false positive
    (no single-letter segment precedes 'home' there, so `/[A-Za-z]/` cannot
    match)."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-msys-fp" / "taskcards.jsonl"
    _write(
        f,
        '{"note": "counts (barcode/cad/cells/home/html/imaging/ocr/page/pdf/psd/tasks/tex/words/zip) identical"}\n',
    )

    findings = rpsp.scan_file(f)
    assert findings == []


def test_does_not_match_placeholder_style_prose(tmp_path):
    """A doc/narrative sentence that already uses angle-bracket placeholder
    syntax (e.g. MT071's own mission_authority.yaml, confirmed live) must
    never be treated as a real leaking path -- '<user>' is not a plausible
    path segment."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-w" / "mission_authority.yaml"
    _write(f, "  mission_summary: containing C:\\Users\\<user>\\... paths in governing_plan_path\n")

    findings = rpsp.scan_file(f)
    assert findings == []


def test_does_not_match_non_home_repo_root_path(tmp_path):
    """Repo-root-shaped absolute paths (no Users/home segment) are out of
    scope -- only the home-directory leak class named in the taskcard."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-v" / "mission_authority.yaml"
    _write(f, "repo_root: D:/onedrive/Documents/GitHub/aspose.org\n")

    findings = rpsp.scan_file(f)
    assert findings == []


def test_trailing_ellipsis_is_not_swept_into_the_match(tmp_path):
    """Real bug found live against reports/plan_state/MT066-.../taskcards.jsonl:
    prose quoting the plan's own D1 decision text ends the path with a bare
    '...' (illustrative truncation, not a further path segment). The '...'
    must not become part of the matched path or its placeholder basename."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-ellipsis" / "taskcards.jsonl"
    _write(
        f,
        '{"note": "local absolute paths embedded (e.g. C:/Users/prora/.claude/plans/... ) get redacted"}\n',
    )

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "C:/Users/prora/.claude/plans"
    assert findings[0].placeholder == "<local-plan-cache>/plans"
    assert "..." not in findings[0].placeholder


def test_does_not_match_home_as_a_family_name_in_a_slash_list(tmp_path):
    """Real false-positive found live against reports/plan_state/
    seo-keyword-production-integration/taskcards.jsonl: an alphabetized
    slash-joined list of product families
    ('barcode/cad/cells/home/html/imaging/.../zip') happens to include one
    literally named 'home', immediately followed by 'html'. This is not a
    Unix home-directory path -- the '/' before 'home' is preceded by 's'
    (from 'cells'), not a token boundary -- and must never be matched."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-family-list" / "taskcards.jsonl"
    _write(
        f,
        '{"note": "counts (barcode/cad/cells/home/html/imaging/ocr/page/pdf/psd/tasks/tex/words/zip) identical"}\n',
    )

    findings = rpsp.scan_file(f)
    assert findings == []


def test_json_escaped_newline_after_path_is_not_swallowed(tmp_path):
    """TC-GOV-01-04: real bug found live in reports/plan_state/readme-
    refresh-pdf-typescript-scale-hardening-2026-09-03/evidence/
    verify-examples.final.result.json -- a captured Node.js stack trace
    inside a JSON string ends the path with a JSON-escaped newline (`\\n`,
    a SINGLE literal backslash) immediately followed by prose, right after
    the path's own DOUBLE-backslash JSON separators. The single stray
    backslash must not be treated as one more path separator that pulls
    the following word into the match/placeholder."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-jsonnewline" / "result.json"
    _write(
        f,
        '{"detail": "at <anonymous> (C:\\\\Users\\\\prora\\\\project\\\\verify_block_6.mts:4\\nconst bytes = doc.Save({"}\n',
    )

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "C:\\\\Users\\\\prora\\\\project\\\\verify_block_6.mts:4"
    assert findings[0].placeholder == "<local-plan-cache>/verify_block_6.mts:4"
    # The unrelated code prose must survive completely untouched.
    text = _read_raw(f)
    assert "\\nconst bytes = doc.Save({" in text
    assert "nconst" not in text.replace("\\nconst", "")


def test_windows_path_does_not_mix_separator_widths_within_one_match(tmp_path):
    """A single-backslash path segment must not extend a match that started
    with double-backslash separators (or vice versa) -- only a single,
    consistent separator width per match, per the tool's own 3-form
    contract (raw single-backslash, JSON double-backslash, forward-slash)."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-mixedsep" / "notes.md"
    # Double-backslash path immediately followed by a SINGLE backslash that
    # is not a real path separator (mirrors the JSON `\n` case, but with an
    # arbitrary letter instead of 'n' to isolate the separator-width bug
    # from any escape-sequence-specific special-casing).
    _write(f, "See C:\\\\Users\\\\prora\\\\plans\\\\one.md\\zextra for details.\n")

    findings = rpsp.scan_file(f)
    assert len(findings) == 1
    assert findings[0].matched_text == "C:\\\\Users\\\\prora\\\\plans\\\\one.md"
    assert findings[0].placeholder == "<local-plan-cache>/one.md"


def test_multiple_occurrences_same_file_all_found(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-multi" / "mission_authority.yaml"
    _write(
        f,
        "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\one.md\n"
        "another_field: C:\\Users\\prora\\.claude\\plans\\two.md\n",
    )

    findings = rpsp.scan_file(f)
    assert len(findings) == 2
    assert findings[0].line_no == 1
    assert findings[1].line_no == 2


@pytest.mark.parametrize(
    "filename",
    [
        "notes.md",
        "notes.txt",
        "result.json",
        "run.log",
        "seed_taskcards.py",
        "MISSION_AUTHORITY.yaml.draft",
        "capture.stderr",
        "change.orig",
        "change.diff",
        "report.html",
        "Example.java",
        "Example.cs",
        "Example.csproj",
        "artifact.sha256",
        "artifact.run_id_self",
    ],
)
def test_scans_every_widened_target_extension(tmp_path, filename):
    """TC-GOV-01-04: every real non-binary extension confirmed present under
    reports/plan_state/** (2026-09-18 live enumeration) must now be scanned,
    not just *.yaml/*.jsonl -- real leaks were found live in .md/.json/.py/
    .txt/.draft files the original TARGET_GLOBS silently skipped."""
    plan_state = tmp_path / "plan_state"
    target = plan_state / "mission-widened" / filename
    _write(target, "See C:\\Users\\prora\\.claude\\plans\\notes.md for details.\n")

    files = rpsp.iter_target_files(plan_state)
    assert target in files

    result = rpsp.check(plan_state)
    assert not result.clean
    assert any(f.file == target for f in result.findings)


def test_does_not_scan_binary_zip_or_whl_extensions(tmp_path):
    """*.zip and *.whl are genuine binary archive formats (confirmed live:
    an MT040 evidence zip, a 3d/python wheel) -- deliberately excluded from
    TARGET_GLOBS so a text regex substitution never runs against (and
    corrupts) a binary container."""
    plan_state = tmp_path / "plan_state"
    zip_file = plan_state / "mission-bin" / "evidence.zip"
    whl_file = plan_state / "mission-bin" / "package.whl"
    zip_file.parent.mkdir(parents=True, exist_ok=True)
    zip_file.write_bytes(b"PK\x03\x04not a real zip but binary-shaped")
    whl_file.write_bytes(b"PK\x03\x04not a real wheel but binary-shaped")

    files = rpsp.iter_target_files(plan_state)
    assert zip_file not in files
    assert whl_file not in files


def test_extensionless_file_is_out_of_scope(tmp_path):
    """The one known real extensionless file under plan_state (BASE_SHA) is
    a bare git SHA that cannot syntactically contain a path -- documented,
    accepted out-of-scope gap, not an oversight."""
    plan_state = tmp_path / "plan_state"
    sha_file = plan_state / "mission-sha" / "BASE_SHA"
    _write(sha_file, "934e700929997ac70a6a080201728c98f932c18c\n")

    files = rpsp.iter_target_files(plan_state)
    assert sha_file not in files


# ---------------------------------------------------------------------------
# Decode-failure hardening (TC-GOV-01-04) -- real non-UTF-8 files exist live
# under the widened scope (cp1252 em-dash bytes in some *.log files); the
# tool must skip them, not crash.
# ---------------------------------------------------------------------------

def test_scan_file_skips_non_utf8_file_without_raising(tmp_path):
    plan_state = tmp_path / "plan_state"
    bad = plan_state / "mission-badenc" / "run.log"
    bad.parent.mkdir(parents=True, exist_ok=True)
    # 0x97 is a cp1252 em-dash byte, not valid standalone UTF-8.
    bad.write_bytes(b"Promote: 3d/java \x97 done\n")

    findings = rpsp.scan_file(bad)
    assert findings == []


def test_check_and_fix_skip_non_utf8_file_without_raising(tmp_path):
    plan_state = tmp_path / "plan_state"
    bad = plan_state / "mission-badenc2" / "run.log"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"Promote: 3d/java \x97 done\n")
    good = plan_state / "mission-badenc2" / "mission_authority.yaml"
    _write(good, "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\ok.md\n")

    result = rpsp.check(plan_state)
    assert len(result.findings) == 1
    assert result.findings[0].file == good

    fix_result = rpsp.fix(plan_state)
    assert good in fix_result.files_fixed
    assert bad not in fix_result.files_fixed
    # The undecodable file's bytes must survive completely untouched.
    assert bad.read_bytes() == b"Promote: 3d/java \x97 done\n"

    assert rpsp.check(plan_state).clean


def test_undecodable_files_reports_the_skip(tmp_path):
    plan_state = tmp_path / "plan_state"
    bad = plan_state / "mission-badenc3" / "run.log"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"no leak here \x97 just a bad byte\n")

    skipped = rpsp.undecodable_files(plan_state)
    assert bad in skipped


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------

def test_check_reports_findings_and_is_not_clean(tmp_path):
    plan_state = tmp_path / "plan_state"
    _write(
        plan_state / "mission-a" / "mission_authority.yaml",
        "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\a.md\n",
    )
    _write(
        plan_state / "mission-b" / "mission_authority.yaml",
        "governing_plan_path: plans/from_backlog/already-relative.md\n",
    )

    result = rpsp.check(plan_state)
    assert not result.clean
    assert len(result.findings) == 1
    assert result.findings[0].file.name == "mission_authority.yaml"


def test_check_clean_when_no_paths_embedded(tmp_path):
    plan_state = tmp_path / "plan_state"
    _write(
        plan_state / "mission-clean" / "mission_authority.yaml",
        "governing_plan_path: plans/from_backlog/already-relative.md\n",
    )

    result = rpsp.check(plan_state)
    assert result.clean
    assert result.findings == []


def test_check_on_missing_directory_is_clean(tmp_path):
    result = rpsp.check(tmp_path / "does-not-exist")
    assert result.clean


# ---------------------------------------------------------------------------
# fix() -- rewrite in place, byte-for-byte preservation of everything else
# ---------------------------------------------------------------------------

def test_fix_rewrites_matched_path_only(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-fix" / "mission_authority.yaml"
    original = (
        "mission_authority:\n"
        "  mission_id: mission-fix\n"
        "  governing_plan_path: C:\\Users\\prora\\.claude\\plans\\mission-fix.md\n"
        "  mission_locked: false\n"
    )
    _write(f, original)

    result = rpsp.fix(plan_state)

    assert result.total_redactions == 1
    assert f in result.files_fixed

    new_text = _read_raw(f)
    expected = (
        "mission_authority:\n"
        "  mission_id: mission-fix\n"
        "  governing_plan_path: <local-plan-cache>/mission-fix.md\n"
        "  mission_locked: false\n"
    )
    assert new_text == expected


def test_fix_preserves_unrelated_content_byte_for_byte(tmp_path):
    """The fix must be a targeted substitution, never a parse-and-rewrite --
    unrelated lines (including odd spacing, comments, unicode) must survive
    untouched."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-preserve" / "mission_authority.yaml"
    original = (
        "mission_authority:\n"
        "  mission_id:   mission-preserve   # trailing comment, odd spacing\n"
        "  mission_summary: 'Unicode check: \u00e9\u00e8\u00fc, emoji \U0001F600'\n"
        "  governing_plan_path: C:\\Users\\prora\\.claude\\plans\\mission-preserve.md\n"
        "  in_scope_outcomes:\n"
        "  - 'Item one'\n"
        "  - 'Item two'\n"
    )
    _write(f, original)

    rpsp.fix(plan_state)
    new_text = _read_raw(f)

    for line in original.splitlines():
        if "governing_plan_path" not in line:
            assert line in new_text
    assert "C:\\Users\\prora" not in new_text
    assert "<local-plan-cache>/mission-preserve.md" in new_text


def test_fix_preserves_crlf_line_endings(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-crlf" / "mission_authority.yaml"
    original = "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\crlf.md\r\nmission_locked: false\r\n"
    _write(f, original, newline="")

    rpsp.fix(plan_state)
    new_text = _read_raw(f)

    assert "\r\n" in new_text
    assert new_text.count("\r\n") == original.count("\r\n")
    assert "<local-plan-cache>/crlf.md" in new_text


def test_fix_handles_multiple_occurrences_in_one_file(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-multi-fix" / "taskcards.jsonl"
    _write(
        f,
        '{"task_id": "TC-01", "source_finding": "C:\\\\Users\\\\prora\\\\.claude\\\\plans\\\\one.md note"}\n'
        '{"task_id": "TC-02", "source_finding": "C:\\\\Users\\\\prora\\\\.claude\\\\plans\\\\two.md note"}\n',
    )

    result = rpsp.fix(plan_state)

    assert result.total_redactions == 2
    new_text = _read_raw(f)
    assert "Users" not in new_text
    assert "<local-plan-cache>/one.md" in new_text
    assert "<local-plan-cache>/two.md" in new_text


def test_fix_skips_files_with_no_findings(tmp_path):
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-noop" / "mission_authority.yaml"
    original = "governing_plan_path: plans/from_backlog/already-relative.md\n"
    _write(f, original)

    result = rpsp.fix(plan_state)

    assert result.files_fixed == []
    assert result.total_redactions == 0
    assert _read_raw(f) == original


def test_check_exits_zero_after_fix_round_trip(tmp_path):
    """The exact acceptance check named in the taskcard: --check exits 0
    after --fix (idempotency of the redaction, not just of the fix pass)."""
    plan_state = tmp_path / "plan_state"
    f = plan_state / "mission-roundtrip" / "mission_authority.yaml"
    _write(f, "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\roundtrip.md\n")

    assert not rpsp.check(plan_state).clean

    rpsp.fix(plan_state)

    assert rpsp.check(plan_state).clean
    # Running fix again must be a true no-op (idempotent).
    second = rpsp.fix(plan_state)
    assert second.files_fixed == []
    assert second.total_redactions == 0


# ---------------------------------------------------------------------------
# CLI (main()) -- exit codes wired through --repo-root
# ---------------------------------------------------------------------------

def _make_repo(tmp_path, plan_path_line):
    repo_root = tmp_path / "repo"
    _write(repo_root / "reports" / "plan_state" / "mission-cli" / "mission_authority.yaml", plan_path_line)
    return repo_root


def test_cli_check_exits_1_when_findings_present(tmp_path, capsys):
    repo_root = _make_repo(tmp_path, "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\cli.md\n")

    exit_code = rpsp.main(["--check", "--repo-root", str(repo_root)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "cli.md" in out


def test_cli_check_exits_0_when_clean(tmp_path):
    repo_root = _make_repo(tmp_path, "governing_plan_path: plans/from_backlog/already-relative.md\n")

    exit_code = rpsp.main(["--check", "--repo-root", str(repo_root)])

    assert exit_code == 0


def test_cli_fix_then_check_round_trip(tmp_path):
    repo_root = _make_repo(tmp_path, "governing_plan_path: C:\\Users\\prora\\.claude\\plans\\cli2.md\n")

    fix_code = rpsp.main(["--fix", "--repo-root", str(repo_root)])
    assert fix_code == 0

    check_code = rpsp.main(["--check", "--repo-root", str(repo_root)])
    assert check_code == 0

    target = repo_root / "reports" / "plan_state" / "mission-cli" / "mission_authority.yaml"
    assert "<local-plan-cache>/cli2.md" in _read_raw(target)


def test_cli_requires_check_or_fix(tmp_path):
    repo_root = _make_repo(tmp_path, "governing_plan_path: plans/x.md\n")
    with pytest.raises(SystemExit):
        rpsp.main(["--repo-root", str(repo_root)])
