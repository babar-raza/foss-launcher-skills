"""Round-trip state-machine test for readme_refresh_run.py, against a scratch fixture --
never a real GitHub repo. Per the plan's own requirement: the fixture deliberately includes
one instance of each of the three real incident classes this plan's checks exist to catch
(a dropped real link, an undisclosed BLOCKING command, a hedging/process-narration sentence)
so this test proves the gates actually fire, not just that the happy path completes.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "foss"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import readme_refresh_run as rr  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    rr.configure()


def _run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


_OLD_UPSTREAM_README = """# Test Product

A test product for the round-trip state machine test.

See [AGENTS.md](AGENTS.md) for contributor guidance.

## Installation

```bash
pip install -e .
```
"""

_GOOD_CANDIDATE = """# Test Product

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

![Test Product](https://products.aspose.org/media/testfam/testplat/banner-readme.png)

## Navigation

- [At a Glance](#at-a-glance)

## At a Glance

```mermaid
flowchart TD
  subgraph StartingPoints["Starting Points"]
    I1["An existing TXT file"]
  end
  PRODUCT["Test Product"]
  subgraph Capabilities["Core Capabilities"]
    C1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    O1["TXT files"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs
```

## Key Capabilities

- Reads and writes TXT files.

## Installation

A PyPI package has not been published yet. Install from source:

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
import testproduct
```

## API Reference

The primary entry point is `TestClass`.

## Documentation & Resources

See [AGENTS.md](AGENTS.md) for contributor guidance.

- Found a bug? [Open an issue](https://github.com/test-org/test-repo/issues).

## Scope and Limitations

- This is a minimal test fixture with a single limitation.

This limitation does not apply to [Test Product — Enterprise Edition](https://products.aspose.com/testfam/testplat/), which adds full production support.

## Development and Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

This project is licensed under the [MIT License](LICENSE). The MIT License permits use,
copying, modification, distribution, sublicensing, and commercial use, provided its copyright
and permission notice are retained. The software is provided without warranty.
"""

# Deliberately defective: (1) drops the AGENTS.md link the old upstream README had, (2) repeats
# the exact command upstream-issues.md marks BLOCKING, (3) includes a process-narration smell.
_BAD_CANDIDATE = _GOOD_CANDIDATE.replace(
    "See [AGENTS.md](AGENTS.md) for contributor guidance.\n\n- Found a bug?",
    "- Found a bug?",
).replace(
    'pip install -e ".[dev]"\n```\n\n## Quick Start',
    'pip install -e .\n```\n\nThis was verified against the published package.\n\n## Quick Start',
)
assert _BAD_CANDIDATE != _GOOD_CANDIDATE, "fixture construction must actually apply both replacements"

_UPSTREAM_ISSUES_BLOCKING = """# Upstream issues — testfam/testplat

Verified: 2026-08-06 against https://github.com/test-org/test-repo @ main

## Broken source install

- **Severity**: BLOCKING (install/build/import fails for any user)
- **Evidence**: `pip install -e .`
- **Impact**: every user hits this
- **Not fixable here because**: upstream packaging bug
"""


def _make_scratch_repo(tmp_path):
    """Build a full scratch environment: data files, a real local git repo standing in for
    both the clone cache AND the external push target, and the report tree readme_refresh_run.py
    writes into. Returns (repo_root, upstream_repo_dir)."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    data_dir = repo_root / "data"
    data_dir.mkdir()

    (data_dir / "products.json").write_text(json.dumps([
        {
            "family": "testfam", "platform": "testplat",
            "repo_name": "test-repo", "repo_url": "https://github.com/test-org/test-repo",
            "clone_url": str(tmp_path / "upstream"), "active": True, "discovered_via": "test",
        }
    ]), encoding="utf-8")
    (data_dir / "registry_exclusions.json").write_text("[]", encoding="utf-8")
    (data_dir / "package_registry.json").write_text("{}", encoding="utf-8")
    (data_dir / "diagram_archetypes.json").write_text("[]", encoding="utf-8")
    (data_dir / "diagram_capability_dependencies.json").write_text("[]", encoding="utf-8")
    # MT025 (Eleventh incident): a real format vocabulary is needed for the fixture's Starting
    # Points/Outputs nodes to pass check_diagram_format_support_claims and the new
    # check_diagram_container_format_purity hard gates.
    (data_dir / "format_descriptions.json").write_text(json.dumps({"TXT": {}}), encoding="utf-8")
    # TC-HARDEN-19 (MT034): a real, resolvable platform-level target matching _GOOD_CANDIDATE's
    # own Enterprise Edition link (https://products.aspose.com/testfam/testplat/) exactly -- so
    # check_enterprise_edition_link_resolves (a hard gate) accepts the shared fixture. Mirrors
    # backlink_targets._lookup_platform's real structure (http_status == 200 is the verification
    # criterion). provenance.generated_at is "now" so target_map_stale is False.
    import datetime as _dt
    (data_dir / "aspose_com_targets.json").write_text(json.dumps({
        "provenance": {"generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
        "targets": {
            "products.aspose.com": {
                "platforms": {
                    "testfam/testplat": {
                        "url": "https://products.aspose.com/testfam/testplat/", "http_status": 200,
                    },
                },
                "families": {},
            },
        },
        "all_urls": {},
    }), encoding="utf-8")
    knowledge_dir = repo_root / "knowledge" / "testfam" / "testplat" / "merged"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "formats.md").write_text(
        "# Format Support\n\n| Format | Import | Export |\n|--------|--------|--------|\n"
        "| TXT | Yes | Yes |\n",
        encoding="utf-8",
    )

    # Real local git repo standing in for the upstream product repo -- clone_url points here,
    # and it's ALSO what gets mirrored into runs/.clone_cache/ below (a real git clone --local
    # is genuinely exercised in the push step, not mocked).
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    (upstream_dir / "README.md").write_text(_OLD_UPSTREAM_README, encoding="utf-8")
    (upstream_dir / "AGENTS.md").write_text("# Contributor guide\n", encoding="utf-8")
    (upstream_dir / "LICENSE").write_text("MIT License\n\nCopyright ...\n", encoding="utf-8")
    # MT027: a real source declaration so check_api_reference_classes_exist_in_reference_site's
    # clone-cache fallback (and check_named_member_accuracy) can confirm `TestClass` is real --
    # there is no reference.aspose.org fixture for "testfam/testplat", so this is the only source.
    (upstream_dir / "test_class.py").write_text("class TestClass:\n    pass\n", encoding="utf-8")
    _run_git(["init", "-q", "-b", "main"], upstream_dir)
    _run_git(["config", "user.email", "test@example.com"], upstream_dir)
    _run_git(["config", "user.name", "Test"], upstream_dir)
    _run_git(["add", "."], upstream_dir)
    _run_git(["commit", "-q", "-m", "initial"], upstream_dir)

    clone_cache_dir = repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
    clone_cache_dir.parent.mkdir(parents=True)
    _run_git(["clone", "--quiet", str(upstream_dir), str(clone_cache_dir)], tmp_path)

    return repo_root, upstream_dir


def _fake_gh_command_runner(preflight_push=True):
    def _runner(cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess.run(cmd, **kwargs)
        if cmd[:2] == ["gh", "api"]:
            class _Result:
                returncode = 0
                stdout = json.dumps({
                    "permissions": {"push": preflight_push, "admin": False},
                    "default_branch": "main", "archived": False, "disabled": False,
                })
                stderr = ""
            return _Result()
        raise AssertionError(f"unexpected command in test: {cmd}")
    return _runner


# Fifteenth incident / MT030 (2026-08-09): a real, correct disposition for both of
# _OLD_UPSTREAM_README's 2 real content units (confirmed via extract_old_readme_content_units
# itself, not guessed) -- u0001 ("A test product for the round-trip state machine test.") is
# generic scene-setting narrative with nothing to verify (category 1); u0002 ("See AGENTS.md...")
# is already present verbatim in _GOOD_CANDIDATE's own Documentation & Resources section, so it's
# a real, checkable redundant-merge case, not a fresh composition. Written by _write_candidate
# below for every existing call site by default -- a test wanting to exercise a MISSING/empty
# disposition file passes dispositions=None/[] explicitly.
_CONTENT_DISPOSITIONS_FOR_SHARED_FIXTURE = [
    {
        "unit_id": "u0001",
        "source": "clone_cache/README.md",
        "excerpt": "A test product for the round-trip state machine test.",
        "salient_tokens": [],
        "classification": "1_narrative_cta",
        "classification_basis": "generic scene-setting sentence, no checkable claim",
        "verification": {"status": "not_applicable_category_1", "evidence_type": None, "evidence_ref": None},
        "disposition": "excluded",
        "target_section": None,
        "excluded_reason": "generic scene-setting narrative, superseded by the new template's own composed intro paragraph",
    },
    {
        "unit_id": "u0002",
        "source": "clone_cache/README.md",
        "excerpt": "See [AGENTS.md](AGENTS.md) for contributor guidance.",
        "salient_tokens": ["AGENTS"],
        "classification": "redundant_with_existing",
        "classification_basis": "already present verbatim in the new candidate's Documentation & Resources section",
        "verification": {
            "status": "verified_redundant",
            "evidence_type": "candidate_section_reference",
            "evidence_ref": "Documentation & Resources",
        },
        "disposition": "merged_verbatim",
        "target_section": "Documentation & Resources",
        "excluded_reason": None,
    },
]


def _write_candidate(
    repo_root, text, upstream_issues=_UPSTREAM_ISSUES_BLOCKING,
    dispositions=_CONTENT_DISPOSITIONS_FOR_SHARED_FIXTURE,
):
    candidate_dir = repo_root / "reports" / "repo-presenter" / "testfam" / "testplat"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "readme.md").write_text(text, encoding="utf-8")
    (candidate_dir / "upstream-issues.md").write_text(upstream_issues, encoding="utf-8")
    if dispositions is not None:
        (candidate_dir / "content-dispositions.json").write_text(
            json.dumps(dispositions), encoding="utf-8"
        )


# --- _detect_dev_test_artifacts (MT029 Item 5) -------------------------------------------------


def test_detect_dev_test_artifacts_finds_real_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Contributor guide\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert detected == [{
        "relative_path": "AGENTS.md", "kind": "agents_guide", "section": "Documentation & Resources",
    }]


def test_detect_dev_test_artifacts_no_windows_case_alias_double_count(tmp_path):
    # Regression test: found live (2026-08-09) on this Windows machine -- AGENTS.md and
    # agents.md both resolve to the same real file on a case-insensitive filesystem, so a
    # naive per-candidate is_file() check registered it twice under two different casings.
    (tmp_path / "AGENTS.md").write_text("# Contributor guide\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert len(detected) == 1


def test_detect_dev_test_artifacts_finds_third_casing_variant(tmp_path):
    # Regression test: found live during the Phase 2 portfolio rollout (2026-08-09,
    # cells/java) -- the real file is cased "Agents.md", a third variant neither of the two
    # literal candidates ("AGENTS.md"/"agents.md") string-equals, so `_add`'s own case-
    # sensitive on-disk-name verification silently rejected both lookups even though the file
    # genuinely exists. A case-insensitive directory scan finds it under any casing.
    (tmp_path / "Agents.md").write_text("# Contributor guide\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert detected == [{
        "relative_path": "Agents.md", "kind": "agents_guide", "section": "Documentation & Resources",
    }]


def test_detect_dev_test_artifacts_excludes_dotdir_pytest_cache(tmp_path):
    # Regression test: found live (2026-08-09, html/python) -- pytest itself writes a
    # boilerplate README.md into `.pytest_cache/` on every test run; "test" is a substring
    # of "pytest_cache", so the original `"test" in name.lower()` check wrongly matched it.
    cache_dir = tmp_path / ".pytest_cache"
    cache_dir.mkdir()
    (cache_dir / "README.md").write_text("This directory is for pytest's cache.\n", encoding="utf-8")
    assert rr._detect_dev_test_artifacts(tmp_path) == []


def test_detect_dev_test_artifacts_still_finds_real_test_dir_readme(tmp_path):
    # Regression guard: excluding dot-directories must never exclude a real, non-dot test
    # directory's own README.md too.
    tests_dir = tmp_path / "Aspose.Cells.Foss.Cpp.Tests"
    tests_dir.mkdir()
    (tests_dir / "README.md").write_text("# Test suite\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert any(a["relative_path"] == "Aspose.Cells.Foss.Cpp.Tests/README.md" for a in detected)


def test_detect_dev_test_artifacts_empty_for_bare_repo(tmp_path):
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    assert rr._detect_dev_test_artifacts(tmp_path) == []


# --- _detect_license_file (TC-HARDEN-20, MT034) ------------------------------------------------


def test_detect_license_file_exact_prefix_still_detected(tmp_path):
    (tmp_path / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026\n", encoding="utf-8")
    result = rr._detect_license_file(tmp_path)
    assert result == {"relative_path": "LICENSE"}


def test_detect_license_file_the_mit_license_mit_variant_now_detected(tmp_path):
    # Regression test: found independently, twice, by two different sub-agents in one real
    # clean-room pilot (barcode/python, cells/cpp) -- both real license files are phrased
    # "The MIT License (MIT)...", undetected by the old exact-20-char-prefix match.
    (tmp_path / "LICENSE").write_text(
        "The MIT License (MIT)\n\nCopyright (c) 2026\n\nPermission is hereby granted...\n",
        encoding="utf-8",
    )
    result = rr._detect_license_file(tmp_path)
    assert result == {"relative_path": "LICENSE"}


def test_detect_license_file_still_rejects_non_mit_license(tmp_path):
    (tmp_path / "LICENSE").write_text(
        "Apache License\nVersion 2.0, January 2004\n\nhttp://www.apache.org/licenses/\n",
        encoding="utf-8",
    )
    assert rr._detect_license_file(tmp_path) is None


def test_detect_license_file_absent_when_no_license_file(tmp_path):
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    assert rr._detect_license_file(tmp_path) is None


# --- _detect_homepage_link (TC-HARDEN-27, MT034) ------------------------------------------------


def test_detect_homepage_link_verified_when_real_index_page_exists(tmp_path):
    repo_root = tmp_path / "repo"
    index_dir = repo_root / "content" / "products.aspose.org" / "en" / "cells" / "cpp"
    index_dir.mkdir(parents=True)
    (index_dir / "_index.md").write_text("---\ntitle: Cells C++\n---\n", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    result = rr._detect_homepage_link("cells", "cpp")
    assert result == {"url": "https://products.aspose.org/cells/cpp/", "verified": True}


def test_detect_homepage_link_unverified_when_no_real_index_page(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rr.configure(repo_root=repo_root)
    result = rr._detect_homepage_link("cells", "cpp")
    assert result == {"url": "https://products.aspose.org/cells/cpp/", "verified": False}


def test_detect_homepage_link_never_confused_by_a_different_platforms_page(tmp_path):
    # Cross-product-contamination guard: a real page for a DIFFERENT platform must not verify
    # this one.
    repo_root = tmp_path / "repo"
    index_dir = repo_root / "content" / "products.aspose.org" / "en" / "cells" / "net"
    index_dir.mkdir(parents=True)
    (index_dir / "_index.md").write_text("---\ntitle: Cells .NET\n---\n", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    result = rr._detect_homepage_link("cells", "cpp")
    assert result["verified"] is False


# --- _detect_enterprise_link (TC-HARDEN-19, MT034) ----------------------------------------------


def _write_target_map(repo_root, targets, *, generated_at=None):
    import datetime as _dt
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "aspose_com_targets.json").write_text(json.dumps({
        "provenance": {
            "generated_at": generated_at or _dt.datetime.now(_dt.timezone.utc).isoformat(),
        },
        "targets": targets,
        "all_urls": {},
    }), encoding="utf-8")


def test_detect_enterprise_link_resolves_real_verified_platform_target(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_target_map(repo_root, {
        "products.aspose.com": {
            "platforms": {"foo/net": {"url": "https://products.aspose.com/foo/net/", "http_status": 200}},
            "families": {},
        },
    })
    rr.configure(repo_root=repo_root)
    result = rr._detect_enterprise_link("foo", "net")
    assert result["url"] == "https://products.aspose.com/foo/net/"
    assert result["type"] == "platform"
    assert result["fallback_reason"] is None
    assert result["target_map_stale"] is False


def test_detect_enterprise_link_falls_back_to_family_when_platform_missing(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_target_map(repo_root, {
        "products.aspose.com": {
            "platforms": {},
            "families": {"foo": {"url": "https://products.aspose.com/foo/", "http_status": 200}},
        },
    })
    rr.configure(repo_root=repo_root)
    result = rr._detect_enterprise_link("foo", "net")
    assert result["url"] == "https://products.aspose.com/foo/"
    assert result["type"] == "family"
    assert result["fallback_reason"] is not None


def test_detect_enterprise_link_returns_none_when_target_map_missing(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "data").mkdir()
    rr.configure(repo_root=repo_root)
    result = rr._detect_enterprise_link("foo", "net")
    assert result["url"] is None
    assert "target_map_unavailable" in result["fallback_reason"]


def test_detect_enterprise_link_returns_none_when_no_target_anywhere(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_target_map(repo_root, {"products.aspose.com": {"platforms": {}, "families": {}}})
    rr.configure(repo_root=repo_root)
    result = rr._detect_enterprise_link("foo", "net")
    assert result["url"] is None
    assert result["fallback_reason"] is not None


def test_detect_enterprise_link_surfaces_target_map_staleness(tmp_path):
    import datetime as _dt
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    stale_date = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=40)).isoformat()
    _write_target_map(repo_root, {
        "products.aspose.com": {
            "platforms": {"foo/net": {"url": "https://products.aspose.com/foo/net/", "http_status": 200}},
            "families": {},
        },
    }, generated_at=stale_date)
    rr.configure(repo_root=repo_root)
    result = rr._detect_enterprise_link("foo", "net")
    assert result["url"] == "https://products.aspose.com/foo/net/"  # stale != wrong -- still used
    assert result["target_map_stale"] is True
    assert result["target_map_age_days"] > 14


# --- TC-HARDEN-30 (MT035): CLI crash-safety -- malformed registries / incomplete rows must ------
# fail with a clean, named ReadmeRefreshRunError, never a raw traceback (KeyError/JSONDecodeError).


def test_load_products_malformed_json_raises_clean_error(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "products.json").write_text("[{\"family\": \"foo\",]", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    with pytest.raises(rr.ReadmeRefreshRunError, match="Malformed JSON"):
        rr._load_products()


def test_load_registry_exclusions_malformed_json_raises_clean_error(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "registry_exclusions.json").write_text("{not valid json", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    with pytest.raises(rr.ReadmeRefreshRunError, match="Malformed JSON"):
        rr._load_registry_exclusions()


def test_resolve_product_missing_repo_url_raises_clean_error(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "products.json").write_text(json.dumps([
        {"family": "foo", "platform": "net", "active": True, "clone_url": "https://example.com/foo.git"}
    ]), encoding="utf-8")
    (repo_root / "data" / "registry_exclusions.json").write_text("[]", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    with pytest.raises(rr.ReadmeRefreshRunError, match="missing required field.*repo_url"):
        rr._resolve_product("foo", "net")


def test_resolve_product_missing_clone_url_raises_clean_error(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "products.json").write_text(json.dumps([
        {"family": "foo", "platform": "net", "active": True, "repo_url": "https://github.com/o/r"}
    ]), encoding="utf-8")
    (repo_root / "data" / "registry_exclusions.json").write_text("[]", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    with pytest.raises(rr.ReadmeRefreshRunError, match="missing required field.*clone_url"):
        rr._resolve_product("foo", "net")


def test_resolve_product_well_formed_row_still_resolves(tmp_path):
    # Regression guard: the new validation must not reject an ordinary, complete row.
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "products.json").write_text(json.dumps([
        {
            "family": "foo", "platform": "net", "active": True,
            "repo_url": "https://github.com/o/r", "clone_url": "https://github.com/o/r.git",
        }
    ]), encoding="utf-8")
    (repo_root / "data" / "registry_exclusions.json").write_text("[]", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    entry = rr._resolve_product("foo", "net")
    assert entry["repo_url"] == "https://github.com/o/r"
    assert entry["clone_url"] == "https://github.com/o/r.git"


# --- Full round-trip happy path ---------------------------------------------------------------


def test_full_round_trip_start_through_push_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-001")
    repo_root, upstream_dir = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    assert manifest["state"] == "INPUTS_PINNED"
    run_id = manifest["run_id"]

    manifest = rr.plan_run("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"
    factpack_path = rr._run_root("testfam", "testplat", run_id) / "facts" / "factpack.json"
    assert factpack_path.is_file()
    factpack = json.loads(factpack_path.read_text(encoding="utf-8"))
    assert factpack["archetype"] == "transform"
    assert factpack["license_file"]["relative_path"] == "LICENSE"
    assert "AGENTS.md" in factpack["old_readme_inventory"]["links"]
    # TC-HARDEN-19 (MT034): the real, live-verified target -- not a guessed slug.
    assert factpack["enterprise_link"]["url"] == "https://products.aspose.com/testfam/testplat/"
    assert factpack["enterprise_link"]["target_map_stale"] is False

    _write_candidate(repo_root, _GOOD_CANDIDATE)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"

    manifest = rr.verify_examples("testfam", "testplat", run_id)
    assert manifest["state"] == "AWAITING_REVIEW"
    upstream_path = rr._upstream_issues_path("testfam", "testplat")
    assert upstream_path.is_file()  # written for every run, even the clean case

    result = rr.recheck("testfam", "testplat", run_id)
    assert result["required_sections"]["findings"] == []
    assert result["enterprise_edition_link_resolves"]["findings"] == []
    assert result["api_reference_table_no_duplicate_rows"]["findings"] == []

    manifest = rr.approve("testfam", "testplat", run_id, note="looks good")
    assert manifest["state"] == "APPROVED"

    manifest = rr.push("testfam", "testplat", run_id, dry_run=True)
    # --dry-run rehearses everything up to (not including) the live write, then returns to
    # APPROVED -- it must never reach PUSHED without a real push.
    assert manifest["state"] == "APPROVED"
    receipt_path = rr._run_root("testfam", "testplat", run_id) / "push" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["dry_run"] is True
    assert receipt["pr_url"] is None
    assert receipt["declared_files"] == ["README.md"]
    # Confirm the disposable clone genuinely happened and produced a real commit (git plumbing
    # actually exercised, not mocked) -- the branch exists in the LOCAL disposable clone with a
    # real README.md change, but --dry-run means it was deliberately never pushed to the
    # upstream remote (the whole point of dry-run is that upstream_dir must NOT see it).
    work_dir = repo_root / "reports" / "readme_refresh_runs" / "_scratch" / f"testfam-testplat-{run_id}"
    assert _run_git(["rev-parse", "--verify", receipt["branch"]], work_dir)
    diff_stat = _run_git(["diff", "--stat", "main", receipt["branch"]], work_dir)
    assert "README.md" in diff_stat
    branches_on_upstream = _run_git(["branch", "-a"], upstream_dir)
    assert receipt["branch"] not in branches_on_upstream

    # TC-HARDEN-15 (MT035): the real, cross-run external-action ledger got exactly one row for
    # this dry-run push.
    ledger_path = repo_root / "reports" / "repo_presenter_actions.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["family"] == "testfam"
    assert rows[0]["platform"] == "testplat"
    assert rows[0]["skill"] == "readme-refresh"
    assert rows[0]["action"] == "readme_push_dry_run"
    assert rows[0]["details"]["dry_run"] is True
    assert rows[0]["details"]["pr_url"] is None
    assert rows[0]["details"]["branch"] == receipt["branch"]
    assert rows[0]["details"]["commit_sha"] == receipt["commit_sha"]


# --- repo_presenter_actions.jsonl ledger (TC-HARDEN-15, MT035) -----------------------------


def test_action_ledger_appends_without_truncating_prior_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h15")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)

    rr._append_action_ledger_row(
        "famone", "platone", action="readme_pr_opened",
        details={"pr_url": "https://example.com/pr/1"}, session_id="s1",
    )
    rr._append_action_ledger_row(
        "famtwo", "plattwo", action="readme_push_dry_run",
        details={"pr_url": None}, session_id="s2",
    )

    ledger_path = repo_root / "reports" / "repo_presenter_actions.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["family"] == "famone"
    assert rows[1]["family"] == "famtwo"
    assert rows[0]["event_id"] != rows[1]["event_id"]


def test_action_ledger_lives_at_reports_root_not_under_a_specific_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h15b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)

    rr._append_action_ledger_row(
        "fam", "plat", action="readme_pr_opened", details={}, session_id="s",
    )
    assert (repo_root / "reports" / "repo_presenter_actions.jsonl").is_file()


# --- Gate-firing proof: the three real incident classes -----------------------------------


def test_ingest_candidate_blocks_on_all_three_incident_classes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-002")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    _write_candidate(repo_root, _BAD_CANDIDATE)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    # Must still be PLANNED -- a failed ingest-candidate must not silently advance.
    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    # 1. Dropped link (AGENTS.md) -- surfaced under dropped_content_uncorrelated, not
    # dropped_content itself, since this shared fixture always has a content-dispositions.json
    # (TC-HARDEN-04's Option B downgrade -- see test_dropped_content_* below for dedicated
    # coverage of both branches). This candidate still fails ingest-candidate overall on the
    # OTHER two hard-gate incident classes below, so the pytest.raises above still holds.
    assert "AGENTS.md" in result["dropped_content_uncorrelated"]["findings"]
    assert result["dropped_content_uncorrelated"]["hard_gate"] is False
    assert result["dropped_content"]["findings"] == []
    # 2. Undisclosed BLOCKING command.
    assert any(f["command"] == "pip install -e ." for f in result["no_undisclosed_blocking_commands"]["findings"])
    # 3. Process-narration smell (heuristic, does not block, but must be surfaced for review).
    assert result["process_narration_smells"]["findings"]

    # Fix the two hard-gate issues (restore the link, remove the blocking command) but
    # deliberately LEAVE the hedging sentence -- it's heuristic, so ingest-candidate must
    # still succeed with it present.
    fixed = _GOOD_CANDIDATE.replace(
        "## Quick start", "This was verified against the published package.\n\n## Quick start"
    )
    _write_candidate(repo_root, fixed)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"


def test_ingest_candidate_blocks_on_unverified_enterprise_link(tmp_path, monkeypatch):
    # TC-HARDEN-19 (MT034, Twentieth incident): reproduces the real, confirmed-live-404
    # 3d/typescript regeneration regression -- a candidate whose Enterprise Edition link was
    # guessed (wrong slug) rather than taken from the factpack's own verified target.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-019")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    bad_link_candidate = _GOOD_CANDIDATE.replace(
        "https://products.aspose.com/testfam/testplat/",
        "https://products.aspose.com/testfam/testplat-guessed-wrong/",
    )
    assert bad_link_candidate != _GOOD_CANDIDATE
    _write_candidate(repo_root, bad_link_candidate)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["enterprise_edition_link_resolves"]["findings"], "must flag the wrong target"
    assert result["enterprise_edition_link_resolves"]["findings"][0]["reason"] == "target_mismatch"


def test_ingest_candidate_blocks_on_duplicate_api_reference_row(tmp_path, monkeypatch):
    # TC-HARDEN-21 (MT034, Twentieth incident): reproduces the real cells/cpp regeneration
    # regression -- an exact-duplicate class row within one API Reference table, undetected by
    # check_api_reference_table_completeness (both occurrences are individually real per the
    # reference index; duplication is a separate defect).
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-021")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    duplicated_row_candidate = _GOOD_CANDIDATE.replace(
        "The primary entry point is `TestClass`.\n",
        "The primary entry point is `TestClass`.\n\n"
        "### Core API\n\n"
        "| Class | Description |\n|---|---|\n"
        "| `TestClass` | The primary entry point. |\n"
        "| `TestClass` | The primary entry point. |\n",
    )
    assert duplicated_row_candidate != _GOOD_CANDIDATE
    _write_candidate(repo_root, duplicated_row_candidate)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    findings = result["api_reference_table_no_duplicate_rows"]["findings"]
    assert findings and findings[0]["class_name"] == "TestClass" and findings[0]["count"] == 2

    # Must still be PLANNED -- a failed ingest-candidate must not silently advance.
    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"

    # Fix the one hard-gate issue (remove the duplicate row) -- must then reach
    # VERIFYING_EXAMPLES cleanly, proving the gate is not merely mechanically triggerable but
    # also correctly releases a genuinely-fixed candidate.
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"


def test_ingest_candidate_blocks_on_license_section_narration(tmp_path, monkeypatch):
    # TC-HARDEN-26 (MT034, Twenty-First incident): reproduces the real, live incident -- a
    # blind clean-room regeneration of 3d/typescript replaced the fixed License template with
    # free-form internal-audit-trail narration.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-026")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    narration_candidate = _GOOD_CANDIDATE.replace(
        "This project is licensed under the [MIT License](LICENSE). The MIT License permits "
        "use,\ncopying, modification, distribution, sublicensing, and commercial use, "
        "provided its copyright\nand permission notice are retained. The software is provided "
        "without warranty.\n",
        "The previous version of this README linked to a LICENSE file, but no LICENSE file "
        "exists anywhere in this repository snapshot -- treat the license status as "
        "unconfirmed.\n",
    )
    assert narration_candidate != _GOOD_CANDIDATE
    _write_candidate(repo_root, narration_candidate)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["license_section_matches_template"]["findings"], "must flag the narration prose"

    # Fix it -- must then reach VERIFYING_EXAMPLES cleanly.
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"


def test_ingest_candidate_blocks_on_unlinked_banner_when_homepage_verified(tmp_path, monkeypatch):
    # TC-HARDEN-27 (MT034, Twenty-First incident): once a real, verified homepage page exists,
    # the banner must be linked to it -- proves the gate actually fires through the real CLI
    # transition, not just the bare function.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-027")
    repo_root, _ = _make_scratch_repo(tmp_path)
    index_dir = repo_root / "content" / "products.aspose.org" / "en" / "testfam" / "testplat"
    index_dir.mkdir(parents=True)
    (index_dir / "_index.md").write_text("---\ntitle: Test Product\n---\n", encoding="utf-8")
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    # _GOOD_CANDIDATE's banner is deliberately the bare, unlinked form -- now genuinely wrong
    # given a real, verified homepage page exists.
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["banner_links_to_homepage"]["findings"], "must flag the unlinked banner"

    linked_candidate = _GOOD_CANDIDATE.replace(
        "![Test Product](https://products.aspose.org/media/testfam/testplat/banner-readme.png)",
        "[![Test Product](https://products.aspose.org/media/testfam/testplat/banner-readme.png)]"
        "(https://products.aspose.org/testfam/testplat/)",
    )
    assert linked_candidate != _GOOD_CANDIDATE
    _write_candidate(repo_root, linked_candidate)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"


# --- TC-HARDEN-12 (MT033): change-isolation gates wired into recheck() ---------------------
#
# check_only_mermaid_block_changed / check_only_sections_changed were real, fully-tested hard
# gates (this plan's own MT024/MT029 idempotency guarantee) that readme_refresh_run.py never
# called -- confirmed by exact-name grep, zero hits, before this fix. These tests prove the
# WIRING actually triggers the gate at the real recheck() transition against a real
# deliberately-cross-contaminated edit, not merely that the underlying functions work in
# isolation (already proven by their own dedicated tests in test_readme_refresh_checks.py).


def _ingest_good_candidate(repo_root, family="testfam", platform="testplat"):
    """Shared setup for the change-isolation tests below: start a run, plan it, ingest the
    shared _GOOD_CANDIDATE fixture -- this is what writes checkpoint 0 (the snapshot every
    recheck() change-isolation check diffs the next edit against)."""
    manifest = rr.start_run(family, platform)
    run_id = manifest["run_id"]
    rr.plan_run(family, platform, run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    manifest = rr.ingest_candidate(family, platform, run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"
    return run_id


def test_recheck_change_isolation_skipped_when_not_requested(tmp_path, monkeypatch):
    # Backward-compat proof: omitting both allowed_headings and mermaid_only (every existing
    # caller, including the round-trip test above) must produce identical behavior to before
    # this change -- no new result.json keys, no crash, no snapshot-dependency at all.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-a")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    result = rr.recheck("testfam", "testplat", run_id)
    assert "change_isolation_mermaid" not in result
    assert "change_isolation_sections" not in result


def test_recheck_change_isolation_skipped_without_prior_snapshot(tmp_path, monkeypatch):
    # A caller can request change-isolation checking even when nothing has ever been ingested
    # yet (e.g. a stray recheck right after plan_run, before ingest_candidate) -- must degrade
    # gracefully (no snapshot to diff against), never crash on a missing file.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)

    result = rr.recheck(
        "testfam", "testplat", run_id, allowed_headings=["Key Capabilities"], mermaid_only=True,
    )
    assert "change_isolation_mermaid" not in result
    assert "change_isolation_sections" not in result


def test_recheck_mermaid_only_fires_on_real_cross_section_contamination(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-c")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    # A real cross-contamination shape: the diagram edit leaks into Key Capabilities too --
    # exactly the class of defect this plan's own MT024 "email/net snapshot contamination"
    # incident (2026-08-05) found live, the incident that originally motivated this gate.
    contaminated = _GOOD_CANDIDATE.replace(
        'C1["Does a thing"]', 'C1["Does a thing well"]',
    ).replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    )
    assert contaminated != _GOOD_CANDIDATE
    _write_candidate(repo_root, contaminated)

    result = rr.recheck("testfam", "testplat", run_id, mermaid_only=True)
    assert result["change_isolation_mermaid"]["hard_gate"] is True
    assert result["change_isolation_mermaid"]["findings"], (
        "mermaid-only claim must be rejected -- Key Capabilities changed too"
    )


def test_recheck_mermaid_only_clean_on_legitimate_diagram_only_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-d")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    diagram_only_edit = _GOOD_CANDIDATE.replace(
        'C1["Does a thing"]', 'C1["Does a thing well"]',
    )
    assert diagram_only_edit != _GOOD_CANDIDATE
    _write_candidate(repo_root, diagram_only_edit)

    result = rr.recheck("testfam", "testplat", run_id, mermaid_only=True)
    assert result["change_isolation_mermaid"]["findings"] == []


def test_recheck_sections_fires_on_undeclared_section_change(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-e")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    # Caller declares this edit is scoped to Key Capabilities only, but Installation changed
    # too -- the exact undeclared-scope shape this gate exists to catch.
    contaminated = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    ).replace(
        'pip install -e ".[dev]"\n```\n\n## Quick Start',
        'pip install -e ".[dev,extra]"\n```\n\n## Quick Start',
    )
    assert contaminated != _GOOD_CANDIDATE
    _write_candidate(repo_root, contaminated)

    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    findings = result["change_isolation_sections"]["findings"]
    assert result["change_isolation_sections"]["hard_gate"] is True
    assert any(f["heading"] == "Installation" for f in findings)
    assert not any(f["heading"] == "Key Capabilities" for f in findings)


def test_recheck_sections_clean_on_legitimate_single_section_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-f")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    single_section_edit = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    )
    assert single_section_edit != _GOOD_CANDIDATE
    _write_candidate(repo_root, single_section_edit)

    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    assert result["change_isolation_sections"]["findings"] == []


def test_recheck_snapshot_rolls_forward_between_calls(tmp_path, monkeypatch):
    # The snapshot is a ROLLING checkpoint (updated after every recheck), not a fixed baseline
    # frozen at first ingest -- a second, independent edit must be diffed against the first
    # edit's own result, not re-flagged against the original candidate.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-g")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    first_edit = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    )
    _write_candidate(repo_root, first_edit)
    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    assert result["change_isolation_sections"]["findings"] == []

    # Second, independent Key-Capabilities-only edit on top of the first -- must still pass,
    # proving the snapshot advanced to first_edit rather than staying pinned to _GOOD_CANDIDATE.
    second_edit = first_edit.replace(
        "- Reads and writes TXT and CSV files.", "- Reads and writes TXT, CSV, and JSON files.",
    )
    assert second_edit != first_edit
    _write_candidate(repo_root, second_edit)
    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    assert result["change_isolation_sections"]["findings"] == []


# --- TC-HARDEN-04 (confirmed live, MT033/e2e, 2026-08-11): dropped_content downgrade ---------
#
# Confirmed necessary, not theoretical: the very first real ingest-candidate run ever made
# through this CLI (3d/typescript) hard-blocked on 9 legitimate, already-disposition-verified
# heading renames + 1 already-disclosed missing-LICENSE link -- since every one of the 30 real
# products adopted the new template's own heading set, this would otherwise hard-block
# ingest-candidate for essentially the entire portfolio. These tests prove both branches of the
# fix, not just the happy path.


def test_dropped_content_downgrades_to_advisory_when_dispositions_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h04-a")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    # A dropped HEADING (not a dropped link) on the CLONE CACHE's own README.md -- isolates the
    # dropped_content-only defect from dev_test_artifacts_linked / content_unit_merged_into_
    # target_section, both of which the shared fixture's AGENTS.md link is independently tied
    # to (dropping THAT link trips those two other, still-hard-gate checks too, which is real
    # and correct but would make this test conflate three defect classes instead of isolating
    # the one this test exists to cover). A bare trailing heading with no body produces no new
    # content unit (extract_old_readme_content_units strips headings before segmenting), so no
    # content_unit_disposition_coverage finding either -- a real, isolated dropped_heading case.
    clone_cache_readme = (
        repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat" / "README.md"
    )
    clone_cache_readme.write_text(
        clone_cache_readme.read_text(encoding="utf-8") + "\n## Roadmap\n", encoding="utf-8",
    )

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    # _GOOD_CANDIDATE has no "## Roadmap" section -- a real, isolated dropped heading, with a
    # content-dispositions.json on file (default fixture) -- must be downgraded, not hard-
    # blocked, and ingest-candidate must succeed.
    _write_candidate(repo_root, _GOOD_CANDIDATE)

    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["dropped_content"]["hard_gate"] is True
    assert result["dropped_content"]["findings"] == []  # internal_labels only, none present
    assert result["dropped_content_uncorrelated"]["hard_gate"] is False
    assert "Roadmap" in result["dropped_content_uncorrelated"]["findings"]


def test_dropped_content_stays_hard_gate_without_dispositions_file(tmp_path, monkeypatch):
    # Regression guard for the pre-fix behavior: a product with NO content-dispositions.json at
    # all (MT030's mechanism has never run for it) must still hard-block on a dropped link --
    # the downgrade is conditional on real disposition accounting existing, never unconditional.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h04-b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    dropped_link_candidate = _GOOD_CANDIDATE.replace(
        "See [AGENTS.md](AGENTS.md) for contributor guidance.\n\n- Found a bug?",
        "- Found a bug?",
    )
    _write_candidate(repo_root, dropped_link_candidate, dispositions=None)

    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert "dropped_content_uncorrelated" not in result
    assert "AGENTS.md" in result["dropped_content"]["findings"]
    assert result["dropped_content"]["hard_gate"] is True


def test_dropped_content_internal_labels_still_hard_gate_with_dispositions_present(tmp_path, monkeypatch):
    # internal_labels is a NEW-candidate-quality check, orthogonal to old-content reuse -- must
    # never be downgraded just because a content-dispositions.json happens to exist.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h04-c")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    internal_label_candidate = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.",
        "- Reads and writes TXT files. (Preserved repository details below.)",
    )
    assert internal_label_candidate != _GOOD_CANDIDATE
    _write_candidate(repo_root, internal_label_candidate)  # default: dispositions present

    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["dropped_content"]["hard_gate"] is True
    assert result["dropped_content"]["findings"], "internal_labels must still block regardless of dispositions"


# --- audit_portfolio / audit-portfolio CLI (TC-HARDEN-05, MT035) --------------------------------
# The real, registered, tested replacement for the ad hoc, gitignored scratch script
# (reports/repo-presenter/_scratch/phase2_scan.py) this session repeatedly hand-wrote/re-derived
# to answer "is the whole portfolio still clean" -- now a real CLI subcommand, testable like any
# other, closing the exact gap TC-HARDEN-14 named (real verification work happening outside any
# registered path).


def _add_second_product(repo_root, *, family="testfam2", platform="testplat2", active=True):
    """Extends the scratch repo's products.json with a second product entry, real enough for
    audit_portfolio to enumerate -- no clone cache/knowledge needed, since a deliberately
    section-incomplete candidate trips check_required_sections (a hard gate needing neither)."""
    products_path = repo_root / "data" / "products.json"
    products = json.loads(products_path.read_text(encoding="utf-8"))
    products.append({
        "family": family, "platform": platform, "repo_name": f"{family}-repo",
        "repo_url": f"https://github.com/test-org/{family}-repo",
        "clone_url": f"https://github.com/test-org/{family}-repo.git",
        "active": active, "discovered_via": "test",
    })
    products_path.write_text(json.dumps(products), encoding="utf-8")


def _write_second_candidate(repo_root, family="testfam2", platform="testplat2"):
    candidate_dir = repo_root / "reports" / "repo-presenter" / family / platform
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "readme.md").write_text("# Incomplete\n\nMissing every required section.\n", encoding="utf-8")


def test_audit_portfolio_reports_clean_and_dirty_products(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    _add_second_product(repo_root)
    _write_second_candidate(repo_root)

    result = rr.audit_portfolio()
    assert result["total"] == 2
    assert result["clean_count"] == 1
    assert result["dirty_count"] == 1
    by_key = {(p["family"], p["platform"]): p for p in result["products"]}
    assert by_key[("testfam", "testplat")]["clean"] is True
    assert by_key[("testfam", "testplat")]["hard_gate_findings"] == {}
    assert by_key[("testfam2", "testplat2")]["clean"] is False
    assert "required_sections" in by_key[("testfam2", "testplat2")]["hard_gate_findings"]
    assert by_key[("testfam2", "testplat2")]["hard_gate_findings"]["required_sections"] > 0
    assert result["skipped"] == []


def test_audit_portfolio_skips_product_with_no_candidate_yet(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    _add_second_product(repo_root)
    # Deliberately do NOT write a candidate for the second product.

    result = rr.audit_portfolio()
    assert result["total"] == 1  # only testfam/testplat was actually checked
    assert result["clean_count"] == 1
    assert result["skipped"] == [{"family": "testfam2", "platform": "testplat2", "reason": "no candidate file yet"}]


def test_audit_portfolio_excludes_inactive_and_registry_excluded_products(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    _add_second_product(repo_root, family="testfam2", platform="testplat2", active=False)
    _write_second_candidate(repo_root, "testfam2", "testplat2")
    _add_second_product(repo_root, family="testfam3", platform="testplat3", active=True)
    _write_second_candidate(repo_root, "testfam3", "testplat3")
    (repo_root / "data" / "registry_exclusions.json").write_text(json.dumps([
        {"match": "family_platform", "family": "testfam3", "platform": "testplat3", "reason": "test exclusion"}
    ]), encoding="utf-8")

    result = rr.audit_portfolio()
    # Only testfam/testplat: testfam2/testplat2 is inactive, testfam3/testplat3 is excluded.
    assert result["total"] == 1
    assert {(p["family"], p["platform"]) for p in result["products"]} == {("testfam", "testplat")}


def test_audit_portfolio_family_platform_filter_narrows_to_one_product(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    _add_second_product(repo_root)
    _write_second_candidate(repo_root)

    result = rr.audit_portfolio(family="testfam2", platform="testplat2")
    assert result["total"] == 1
    assert result["products"][0]["family"] == "testfam2"


def test_audit_portfolio_cli_prints_summary(tmp_path, capsys):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _write_candidate(repo_root, _GOOD_CANDIDATE)

    exit_code = rr.main(["audit-portfolio"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "1/1 products ALL HARD GATES CLEAN" in out


def test_audit_portfolio_cli_json_flag_prints_structured_output(tmp_path, capsys):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _write_candidate(repo_root, _GOOD_CANDIDATE)

    exit_code = rr.main(["audit-portfolio", "--json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["clean_count"] == 1


# --- Illegal transition rejection -----------------------------------------------------------


def test_illegal_transition_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-003")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    assert manifest["state"] == "INPUTS_PINNED"

    # approve() requires AWAITING_REVIEW; calling it straight after start (INPUTS_PINNED) must
    # be rejected by the state machine, not silently succeed.
    with pytest.raises(rr.ReadmeRefreshRunError, match="Illegal"):
        rr._transition(manifest, "APPROVED")


# --- Locking: a second run for the same product while one is active must refuse -----------


def test_second_run_for_same_product_refused_while_active(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-004")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    rr.start_run("testfam", "testplat")
    with pytest.raises(rr.ReadmeRefreshRunError, match="already has active run"):
        rr.start_run("testfam", "testplat")


# --- Family-registry consistency (TC-HARDEN-33, MT035) -------------------------------------


def test_start_run_refuses_unregistered_family(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h33-a")
    repo_root, _ = _make_scratch_repo(tmp_path)
    (repo_root / "data" / "families.json").write_text(
        json.dumps({"otherfam": "Aspose.OtherFam"}), encoding="utf-8"
    )
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    with pytest.raises(rr.ReadmeRefreshRunError, match="not registered in data/families.json"):
        rr.start_run("testfam", "testplat")


def test_start_run_succeeds_for_registered_family(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h33-b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    (repo_root / "data" / "families.json").write_text(
        json.dumps({"testfam": "Aspose.TestFam"}), encoding="utf-8"
    )
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    assert manifest["state"] == "INPUTS_PINNED"


def test_start_run_degrades_gracefully_when_families_json_absent(tmp_path, monkeypatch):
    # Regression guard: families.json itself missing is a different, unrelated problem -- must
    # not block every single run just because that file doesn't exist at all.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h33-c")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    assert manifest["state"] == "INPUTS_PINNED"


# --- Git-dirty reference-index-source detection (TC-HARDEN-37, MT035) ----------------------


def _make_real_git_repo_with_reference_index(tmp_path):
    """A genuine git repo (not the scratch fixture's plain directory) -- needed to exercise
    _reference_index_source_dirty's real `git diff --stat HEAD` behavior, not a mock."""
    repo_root = tmp_path / "real_git_repo"
    repo_root.mkdir()
    index_dir = repo_root / "content" / "reference.aspose.org" / "en" / "testfam" / "testplat"
    index_dir.mkdir(parents=True)
    (index_dir / "_index.md").write_text("## Core API\n\n| Class | Description |\n", encoding="utf-8")
    _run_git(["init", "-q", "-b", "main"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test"], repo_root)
    _run_git(["add", "."], repo_root)
    _run_git(["commit", "-q", "-m", "initial"], repo_root)
    return repo_root, index_dir / "_index.md"


def test_reference_index_source_dirty_false_when_clean(tmp_path):
    repo_root, _ = _make_real_git_repo_with_reference_index(tmp_path)
    rr.configure(repo_root=repo_root)
    assert rr._reference_index_source_dirty("testfam", "testplat") is False


def test_reference_index_source_dirty_true_when_uncommitted_edit_exists(tmp_path):
    repo_root, index_path = _make_real_git_repo_with_reference_index(tmp_path)
    index_path.write_text(
        "## Core API\n\n| Class | Description |\n|---|---|\n| `NewClass` | New. |\n", encoding="utf-8"
    )
    rr.configure(repo_root=repo_root)
    assert rr._reference_index_source_dirty("testfam", "testplat") is True


def test_reference_index_source_dirty_false_when_no_git_repo_at_all(tmp_path):
    # Regression guard: repo_root that isn't a git repository at all (e.g. the scratch test
    # fixture's own plain directory) must degrade gracefully, never raise.
    repo_root = tmp_path / "not_a_git_repo"
    repo_root.mkdir()
    rr.configure(repo_root=repo_root)
    assert rr._reference_index_source_dirty("testfam", "testplat") is False


def test_run_deterministic_checks_surfaces_dirty_reference_index_as_heuristic(tmp_path):
    repo_root, index_path = _make_real_git_repo_with_reference_index(tmp_path)
    index_path.write_text(
        "## Core API\n\n| Class | Description |\n|---|---|\n| `NewClass` | New. |\n", encoding="utf-8"
    )
    rr.configure(repo_root=repo_root)
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    result = rr._run_deterministic_checks("testfam", "testplat", _GOOD_CANDIDATE, clone_cache)
    assert result["reference_index_source_dirty"]["hard_gate"] is False
    assert result["reference_index_source_dirty"]["findings"], "must fire when the source is genuinely dirty"


# --- Pre-flight access check: real refusal on push: false ----------------------------------


def test_preflight_refuses_without_push_access(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-005")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner(preflight_push=False))

    with pytest.raises(rr.ReadmeRefreshRunError, match="No push/admin access"):
        rr.start_run("testfam", "testplat")


# --- BLOCKED -> recover ----------------------------------------------------------------------


def test_blocked_run_recovers_to_resume_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-006")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    manifest = rr.status("testfam", "testplat", run_id)
    rr._block(manifest, "simulated failure for recovery test")
    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "BLOCKED"
    assert manifest["resume_state"] == "PLANNED"

    manifest = rr.recover_run("testfam", "testplat", run_id, reason="retrying after simulated failure")
    assert manifest["state"] == "PLANNED"


# --- verify-examples gates on all_named -----------------------------------------------------


def test_verify_examples_refuses_when_not_all_named(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-007")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(
        repo_root=repo_root, command_runner=_fake_gh_command_runner(),
        verification_runner=lambda candidate_path, factpack: {"runner": "incomplete", "all_named": False},
    )

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    rr.ingest_candidate("testfam", "testplat", run_id)

    with pytest.raises(rr.ReadmeRefreshRunError, match="no named status"):
        rr.verify_examples("testfam", "testplat", run_id)

    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"  # must not have advanced


# --- TC-HARDEN-01 (MT033): python_verification_runner ---------------------------------------
#
# Real acquire->execute->classify is the check (never mocked) -- but the network-dependent half
# (a real `pip install` from PyPI) is deliberately NOT exercised here, to keep the committed
# suite fast and network-independent, matching this plan's own established practice (the
# original 2026-08-03/04 verification sprint was itself a real, manual, one-time pass, never a
# committed automated test either). These tests use the CURRENT test-running interpreter
# directly (no new venv) to prove the classify/execute logic for real, and a real (but purely
# local, no-network) venv creation to prove the acquire logic's real failure paths. The full
# real-PyPI acquire path was separately, manually proven end-to-end against a real product
# (see this plan's own TC-HARDEN-01 closure record for the exact command and result).


def test_run_single_python_block_clean_execution(tmp_path):
    result = rr._run_single_python_block(sys.executable, "print('hello')", tmp_path, 0)
    assert result == {"index": 0, "status": "COMPILED+RAN CLEAN"}


def test_run_single_python_block_runtime_error_captured(tmp_path):
    result = rr._run_single_python_block(
        sys.executable, "raise ValueError('boom, real traceback')", tmp_path, 1,
    )
    assert result["index"] == 1
    assert result["status"] == "BLOCKED-WITH-REASON"
    assert result["reason"] == "RUNTIME-ERROR"
    assert "boom, real traceback" in result["detail"]


def test_acquire_python_environment_real_venv_unpublished_no_clone_cache(tmp_path):
    # Real venv creation (no network -- python -m venv is purely local), then the real,
    # honest failure when unpublished and no clone cache exists to editable-install from.
    result = rr._acquire_python_environment(
        tmp_path, {"published": False, "candidate": {"name": "doesnt-matter"}},
        tmp_path / "no-such-clone-cache",
    )
    assert result["ok"] is False
    assert "no clone cache directory" in result["detail"]
    # The venv itself was still really created before the failure -- confirm it exists on disk.
    assert (tmp_path / "venv").is_dir()


def test_python_verification_runner_non_python_blocks_stay_stub(tmp_path):
    candidate_path = tmp_path / "readme.md"
    candidate_path.write_text(
        "## Installation\n\n```bash\npip install -e .\n```\n\n"
        "## Quick Start\n\n```csharp\nvar x = 1;\n```\n",
        encoding="utf-8",
    )
    result = rr.python_verification_runner(candidate_path, {"family": "testfam", "platform": "testplat"})
    assert result["runner"] == "python_verification_runner_v1"
    assert result["blocks_found"] == 2
    assert result["all_named"] is True
    assert all(b["status"] == "BLOCKED-WITH-REASON" and b["reason"] == "TOOLCHAIN-UNAVAILABLE"
               for b in result["block_statuses"])


def test_python_verification_runner_real_local_editable_install_and_execution(tmp_path):
    # Fully real acquire->execute->classify, but zero network dependency: a real, minimal,
    # locally-buildable package (legacy setup.py, no pyproject.toml -- avoids pip needing to
    # fetch a PEP 517 build backend from PyPI) stands in for the clone cache, so `pip install -e`
    # is a genuine editable install with nothing fetched from the network.
    clone_cache_root = tmp_path / "clone_cache_root"
    clone_cache = clone_cache_root / "aspose_testfam_testplat"
    clone_cache.mkdir(parents=True)
    (clone_cache / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='testpkg_e2e', version='0.1', py_modules=['testpkg_e2e'])\n",
        encoding="utf-8",
    )
    (clone_cache / "testpkg_e2e.py").write_text("VALUE = 42\n", encoding="utf-8")
    rr.configure(clone_cache_root=clone_cache_root)

    candidate_path = tmp_path / "readme.md"
    candidate_path.write_text(
        "## Quick Start\n\n```python\nimport testpkg_e2e\nassert testpkg_e2e.VALUE == 42\n```\n",
        encoding="utf-8",
    )
    result = rr.python_verification_runner(
        candidate_path, {"family": "testfam", "platform": "testplat", "install": {"published": False}},
    )
    assert result["blocks_found"] == 1
    status = result["block_statuses"][0]
    assert status["status"] == "COMPILED+RAN CLEAN", status


# --- Stale-input-forces-replan at approve ---------------------------------------------------


def test_approve_forces_replan_on_pinned_input_drift(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-008")
    repo_root, upstream_dir = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    rr.ingest_candidate("testfam", "testplat", run_id)
    rr.verify_examples("testfam", "testplat", run_id)

    # Simulate real drift: the clone cache's HEAD moves after inputs were pinned.
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    (clone_cache / "extra-file.txt").write_text("new content\n", encoding="utf-8")
    _run_git(["add", "."], clone_cache)
    _run_git(["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "drift"], clone_cache)

    with pytest.raises(rr.ReadmeRefreshRunError, match="drifted"):
        rr.approve("testfam", "testplat", run_id, note="approving despite drift")

    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"  # forced back, never silently approved
