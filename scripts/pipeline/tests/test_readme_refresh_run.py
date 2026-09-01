"""Round-trip state-machine test for readme_refresh_run.py, against a scratch fixture --
never a real GitHub repo. Per the plan's own requirement: the fixture deliberately includes
one instance of each of the three real incident classes this plan's checks exist to catch
(a dropped real link, an undisclosed BLOCKING command, a hedging/process-narration sentence)
so this test proves the gates actually fire, not just that the happy path completes.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "foss"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import readme_refresh_run as rr  # noqa: E402
import publication_reconciler  # noqa: E402


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

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Contributors](https://img.shields.io/github/contributors/test-org/test-repo.svg)](https://github.com/test-org/test-repo/graphs/contributors)

![Test Product](https://products.aspose.org/media/testfam/testplat/banner-readme.png)

## Navigation

- [At a Glance](#at-a-glance)
- [Key Capabilities](#key-capabilities)
- [Installation](#installation)
- [Dependencies](#dependencies)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Documentation & Resources](#documentation--resources)
- [Scope and Limitations](#scope-and-limitations)
- [Development and Testing](#development-and-testing)
- [License](#license)

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

## Dependencies

### Required Package Dependencies

- `requests` >=2.0 -- HTTP client used for remote format validation.

### Native and System Requirements

- Requires Python 3.9 or later.

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
    'pip install -e ".[dev]"\n```\n\n## Dependencies',
    'pip install -e .\n```\n\n## Dependencies',
).replace(
    "## Quick Start",
    "This was verified against the published package.\n\n## Quick Start",
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
    # Thirty-First incident / MT041 (2026-08-14): "testplat" is a synthetic platform with no
    # real ecosystem in dependency_extract._PLATFORM_ECOSYSTEM -- a real, provenance-carrying
    # override (matching the shared _GOOD_CANDIDATE fixture's own real "requests" dependency
    # bullet) is the correct, non-hacky way to make this fixture pass through real dependency-
    # extraction machinery, exactly the sanctioned escape hatch a genuinely new/unrecognized
    # platform is designed to use.
    (data_dir / "dependency_overrides.json").write_text(json.dumps({
        "testfam/testplat": {
            "ecosystem": "pypi", "source_manifest_path": "pyproject.toml",
            "verified_by": "test-fixture", "verified_at": "2026-08-14",
            "evidence_note": "synthetic test fixture -- testplat has no real ecosystem",
            "required": [{"name": "requests", "version_constraint": ">=2.0"}],
        },
    }), encoding="utf-8")
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

    # RC-readme-refresh-freshness-guard-compliance (2026-08-30): plan_run() now hard-gates on
    # freshness_guard.is_generation_allowed() (degraded mode) before doing any work -- without a
    # real model.yaml here, every test through this shared fixture would BLOCK at plan_run with
    # PROVENANCE_MISSING. Mirrors test_refresh_run.py's own established _isolate-fixture
    # precedent for the identical FRESH-001 migration (family/platform/repo_sha/stale_since is
    # the minimum freshness_guard.check_freshness needs to resolve CURRENT in degraded mode --
    # degraded mode never verifies repo_sha against the clone, so the real HEAD sha here is for
    # authenticity, not correctness).
    real_head = _run_git(["rev-parse", "HEAD"], upstream_dir)
    (knowledge_dir / "model.yaml").write_text(
        f"family: testfam\nplatform: testplat\nrepo_sha: {real_head}\nstale_since: null\n",
        encoding="utf-8",
    )

    # RC-banner-asset-existence (readme-refresh-hardening-and-regen-2026-08-30): the new
    # check_banner_asset_exists hard gate needs a real file on disk at the path _GOOD_CANDIDATE's
    # own banner line names -- without this, every test through this shared fixture would report
    # a spurious banner_asset_exists finding.
    banner_dir = repo_root / "static" / "media" / "testfam" / "testplat"
    banner_dir.mkdir(parents=True)
    (banner_dir / "banner-readme.png").write_bytes(b"\x89PNG\r\n\x1a\n")

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

# Twenty-Fourth mission (2026-08-13): _OLD_UPSTREAM_README's own "## Installation" section is
# ENTIRELY a fenced `pip install -e .` block with zero surrounding prose -- confirmed via a
# direct extract_old_readme_structural_units() run, not guessed -- so it is a real, genuine
# structural unit (kind: generic_structural_block, no claimed_paths) that every shared-fixture
# test must account for now that the two new hard gates are wired in. Disposition: merged into
# the candidate's own existing "## Installation" section, which already contains a real fenced
# bash block, satisfying check_structural_unit_merged_into_target_section's generic-block rule.
_STRUCTURE_DISPOSITIONS_FOR_SHARED_FIXTURE = [
    {
        "unit_id": "s0001",
        "disposition": "merged_reframed",
        "target_section": "Installation",
        "claimed_paths": None,
        "excluded_reason": None,
        "verification": {
            "status": "verified_against_source",
            "evidence_type": "clone_cache_path",
            "evidence_ref": "README.md",
        },
    },
]


# Thirty-Seventh incident / MT047 (2026-08-15): _OLD_UPSTREAM_README's own "## Installation"
# section is entirely a fenced `pip install -e .` bash block (the same one already accounted for
# as structural unit s0001 above) -- confirmed via a direct extract_old_readme_code_units() run,
# not guessed: exactly one real code unit, c0001, fingerprint ["pip install"]. Disposed merged
# into the candidate's own "## Installation" section, which contains its own real
# `pip install -e ".[dev]"` bash block -- same fingerprint token ("pip install"), so check_code_
# example_api_coverage_survives resolves cleanly.
_CODE_EXAMPLE_DISPOSITIONS_FOR_SHARED_FIXTURE = [
    {
        "unit_id": "c0001",
        "heading_context": "Installation",
        "language": "bash",
        "api_call_fingerprint": ["pip install"],
        "disposition": "merged_reframed",
        "target_section": "Installation",
        "excluded_reason": None,
        "verification": {
            "status": "verified_against_source",
            "evidence_type": "clone_cache_path",
            "evidence_ref": "README.md",
        },
    },
]


def _write_candidate(
    repo_root, text, upstream_issues=_UPSTREAM_ISSUES_BLOCKING,
    dispositions=_CONTENT_DISPOSITIONS_FOR_SHARED_FIXTURE,
    structure_dispositions=_STRUCTURE_DISPOSITIONS_FOR_SHARED_FIXTURE,
    badge_dispositions=None,
    code_example_dispositions=_CODE_EXAMPLE_DISPOSITIONS_FOR_SHARED_FIXTURE,
):
    # MT055/TC-MICRO-03: resolved dynamically via the real path helper (not a hardcoded literal)
    # so this shared fixture always writes into whichever tree the test's own configure() call
    # is actually pointed at -- stays correct across the default-candidate-tree-name change.
    candidate_dir = rr._candidate_readme_path("testfam", "testplat").parent
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "readme.md").write_text(text, encoding="utf-8")
    (candidate_dir / "upstream-issues.md").write_text(upstream_issues, encoding="utf-8")
    if dispositions is not None:
        (candidate_dir / "content-dispositions.json").write_text(
            json.dumps(dispositions), encoding="utf-8"
        )
    if structure_dispositions is not None:
        (candidate_dir / "structure-dispositions.json").write_text(
            json.dumps(structure_dispositions), encoding="utf-8"
        )
    # badge_dispositions defaults to None (no file written): _OLD_UPSTREAM_README has zero real
    # badges, so an absent structure-dispositions.json-shaped file and a missing badge-
    # dispositions.json both correctly resolve to a vacuous [] -- nothing to write for the shared
    # fixture's default case; a test exercising badge dispositions for real passes its own list.
    if badge_dispositions is not None:
        (candidate_dir / "badge-dispositions.json").write_text(
            json.dumps(badge_dispositions), encoding="utf-8"
        )
    if code_example_dispositions is not None:
        (candidate_dir / "code-example-dispositions.json").write_text(
            json.dumps(code_example_dispositions), encoding="utf-8"
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


# --- _repo_full_name / _detect_available_badges (TC-HARDEN-57, MT042) ---------------------------


def _write_products_json(repo_root, entries):
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "products.json").write_text(json.dumps(entries), encoding="utf-8")


def test_repo_full_name_resolves_real_entry(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_products_json(repo_root, [
        {"family": "cells", "platform": "cpp", "repo_url": "https://github.com/org/repo/"},
    ])
    rr.configure(repo_root=repo_root)
    assert rr._repo_full_name("cells", "cpp") == "org/repo"


def test_repo_full_name_none_when_no_matching_entry(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_products_json(repo_root, [])
    rr.configure(repo_root=repo_root)
    assert rr._repo_full_name("cells", "cpp") is None


def test_repo_full_name_none_when_products_json_absent(tmp_path):
    # Must never raise -- a badge-availability query is a best-effort enrichment, not a
    # load-bearing input, unlike _load_products()'s other callers.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rr.configure(repo_root=repo_root)
    assert rr._repo_full_name("cells", "cpp") is None


def test_repo_full_name_none_when_repo_url_not_github(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_products_json(repo_root, [
        {"family": "cells", "platform": "cpp", "repo_url": "https://gitlab.com/org/repo"},
    ])
    rr.configure(repo_root=repo_root)
    assert rr._repo_full_name("cells", "cpp") is None


def test_detect_available_badges_license_available_when_real_license_file():
    result = rr._detect_available_badges(
        "cells", "cpp", repo_full_name=None, license_file={"relative_path": "LICENSE"},
        install_info={}, dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["license"]["available"] is True
    assert result["license"]["link_url"] == "LICENSE"


def test_detect_available_badges_license_unavailable_when_no_license_file():
    result = rr._detect_available_badges(
        "cells", "cpp", repo_full_name=None, license_file=None,
        install_info={}, dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["license"]["available"] is False


def test_detect_available_badges_package_version_pypi_published():
    result = rr._detect_available_badges(
        "cells", "python", repo_full_name=None, license_file=None,
        install_info={
            "published": True, "registry_type": "pypi",
            "candidate": {"name": "aspose-cells-foss"},
        },
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["package_version"]["available"] is True
    assert result["package_version"]["image_url"] == "https://img.shields.io/pypi/v/aspose-cells-foss.svg"


def test_detect_available_badges_package_version_maven_uses_group_and_artifact():
    result = rr._detect_available_badges(
        "cells", "java", repo_full_name=None, license_file=None,
        install_info={
            "published": True, "registry_type": "maven",
            "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss"},
        },
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["package_version"]["available"] is True
    assert "org.aspose/aspose-cells-foss" in result["package_version"]["image_url"]


def test_detect_available_badges_package_version_unpublished_is_unavailable():
    result = rr._detect_available_badges(
        "cells", "typescript", repo_full_name=None, license_file=None,
        install_info={
            "published": False, "registry_type": "npm", "candidate": {"name": "excel-cells"},
        },
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["package_version"]["available"] is False


def test_detect_available_badges_package_version_go_modules_unavailable():
    # Real, disclosed correction against the original design table: Go modules are decentralized
    # -- no real package-version-registry badge exists (see the module docstring).
    result = rr._detect_available_badges(
        "cells", "go", repo_full_name=None, license_file=None,
        install_info={
            "published": True, "registry_type": "go_modules",
            "candidate": {"module_path": "github.com/org/repo/v26"},
        },
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["package_version"]["available"] is False


def test_detect_available_badges_language_version_from_native_system():
    # Real, verified: only the Go extractor currently populates native_system with a version
    # floor (dependency_extract.py, confirmed by direct code read).
    result = rr._detect_available_badges(
        "cells", "go", repo_full_name=None, license_file=None, install_info={},
        dependency_snapshot={"native_system": [{"name": "go", "version_constraint": "1.24.5"}]},
        dev_test_artifacts=[],
    )
    assert result["language_version"]["available"] is True
    assert "1.24.5%2B" in result["language_version"]["image_url"]
    assert "00ADD8" in result["language_version"]["image_url"]


def test_detect_available_badges_language_version_python_pypi_pyversions():
    result = rr._detect_available_badges(
        "cells", "python", repo_full_name=None, license_file=None,
        install_info={
            "published": True, "registry_type": "pypi",
            "candidate": {"name": "aspose-cells-foss"},
        },
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["language_version"]["available"] is True
    assert result["language_version"]["image_url"] == "https://img.shields.io/pypi/pyversions/aspose-cells-foss.svg"


def test_detect_available_badges_language_version_unavailable_for_java_with_no_native_system():
    # Real, disclosed narrowing: Java's real toolchain floor exists in shipped content, but
    # dependency_extract's Maven extractor never populates native_system -- honestly unavailable.
    result = rr._detect_available_badges(
        "cells", "java", repo_full_name=None, license_file=None, install_info={},
        dependency_snapshot={"native_system": []}, dev_test_artifacts=[],
    )
    assert result["language_version"]["available"] is False


def test_detect_available_badges_ci_build_status_from_real_workflow():
    result = rr._detect_available_badges(
        "cells", "go", repo_full_name="org/repo", license_file=None, install_info={},
        dependency_snapshot=None,
        dev_test_artifacts=[{"relative_path": ".github/workflows/ci.yml", "kind": "ci_workflow", "section": "x"}],
    )
    assert result["ci_build_status"]["available"] is True
    assert result["ci_build_status"]["image_url"] == "https://github.com/org/repo/actions/workflows/ci.yml/badge.svg"


def test_detect_available_badges_ci_build_status_unavailable_with_no_workflow():
    result = rr._detect_available_badges(
        "cells", "go", repo_full_name="org/repo", license_file=None, install_info={},
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["ci_build_status"]["available"] is False


def test_detect_available_badges_contributor_count_from_repo_full_name():
    result = rr._detect_available_badges(
        "cells", "go", repo_full_name="org/repo", license_file=None, install_info={},
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["contributor_count"]["available"] is True
    assert result["contributor_count"]["image_url"] == "https://img.shields.io/github/contributors/org/repo.svg"


def test_detect_available_badges_contributor_count_unavailable_with_no_repo_full_name():
    result = rr._detect_available_badges(
        "cells", "go", repo_full_name=None, license_file=None, install_info={},
        dependency_snapshot=None, dev_test_artifacts=[],
    )
    assert result["contributor_count"]["available"] is False


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


# --- _classify_enterprise_relationship / _load_canonical_overrides (TC-HARDEN-61, MT043,
# Thirty-Third incident; CORRECTED 2026-08-14, MT044, Thirty-Fourth incident) ---------------------
# Trigger: cells/typescript's README linked "Aspose.Cells for .NET -- Enterprise Edition" to a
# family-level URL that has nothing specifically to do with .NET. _detect_enterprise_link has
# always correctly resolved WHICH url to use; nothing ever classified WHAT that url represents
# relative to the source product, so the composing agent was free to write any platform name.
# MT044 correction: the original "exact"/"bridge" split (and its required "via {language}"
# disclosure wording) is reversed -- both collapse into one "platform" relationship carrying only
# a normalized, implementation-neutral `public_platform` name. No field here may ever again carry
# implementation-bridge information (`destination_platform`/`bridge_language` are gone).


def test_classify_enterprise_relationship_family_when_no_trailing_segment():
    result = rr._classify_enterprise_relationship("typescript", "https://products.aspose.com/cells/")
    assert result == {"relationship": "family", "public_platform": None}


def test_classify_enterprise_relationship_platform_for_exact_segment():
    # Real, captured shape: cells/java resolves to .../cells/java/ -- exact platform counterpart.
    result = rr._classify_enterprise_relationship("java", "https://products.aspose.com/cells/java/")
    assert result == {"relationship": "platform", "public_platform": "Java"}


def test_classify_enterprise_relationship_platform_for_compound_slug_names_leading_platform_only():
    # Real, captured shape: cells/go resolves to .../cells/go-cpp/ -- a real, verified page. The
    # anchor must name only "Go" (the leading/public component) -- never expose "C++" anywhere.
    result = rr._classify_enterprise_relationship("go", "https://products.aspose.com/cells/go-cpp/")
    assert result == {"relationship": "platform", "public_platform": "Go"}


def test_classify_enterprise_relationship_platform_recognizes_compound_slugs_python_and_nodejs():
    cases = [
        ("https://products.aspose.com/cells/python-net/", "Python"),
        ("https://products.aspose.com/cells/python-java/", "Python"),
        ("https://products.aspose.com/barcode/nodejs-cpp/", "Node.js"),
    ]
    for url, expected_public_platform in cases:
        result = rr._classify_enterprise_relationship("python", url)
        assert result["relationship"] == "platform", url
        assert result["public_platform"] == expected_public_platform, url


def test_classify_enterprise_relationship_unresolved_for_unrecognized_compound_leading_segment():
    result = rr._classify_enterprise_relationship("python", "https://products.aspose.com/cells/xyz-rust/")
    assert result["relationship"] == "unresolved"
    assert result["public_platform"] is None


def test_classify_enterprise_relationship_unresolved_when_non_hyphen_segment_is_a_different_platform():
    # A genuinely different, non-compound platform slug that does NOT match the source product's
    # own platform -- per the plan's own explicit rule, never silently defaulted to "platform"
    # using the destination's own name; this shape should not occur in practice (resolve_backlink
    # only ever resolves per-source-platform targets) but must fail safe, not guess, if it does.
    result = rr._classify_enterprise_relationship("typescript", "https://products.aspose.com/cells/java/")
    assert result == {"relationship": "unresolved", "public_platform": None}


def test_classify_enterprise_relationship_none_when_url_is_none():
    result = rr._classify_enterprise_relationship("typescript", None)
    assert result == {"relationship": None, "public_platform": None}


def test_classify_enterprise_relationship_idempotent():
    a = rr._classify_enterprise_relationship("go", "https://products.aspose.com/cells/go-cpp/")
    b = rr._classify_enterprise_relationship("go", "https://products.aspose.com/cells/go-cpp/")
    assert a == b


def test_detect_enterprise_link_folds_relationship_fields_for_real_cells_typescript_shape(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_target_map(repo_root, {
        "products.aspose.com": {
            "platforms": {},
            "families": {"cells": {"url": "https://products.aspose.com/cells/", "http_status": 200}},
        },
    })
    rr.configure(repo_root=repo_root)
    result = rr._detect_enterprise_link("cells", "typescript")
    assert result["relationship"] == "family"
    assert result["public_platform"] is None
    assert "destination_platform" not in result
    assert "bridge_language" not in result


def test_detect_enterprise_link_uses_canonical_override_over_stale_raw_cache(tmp_path):
    # Reproduces the real, confirmed cells/python fix: the override file's own dated policy says
    # python-net; the raw cached target map (a later, less-explained "manual correction") instead
    # held python-java. Without loading the override, /readme-refresh silently used the less-
    # authoritative value -- this proves the fix, not just that the override file parses. The
    # anchor consequence (MT044) is identical either way -- "Python" -- but the real URL must be
    # the authoritative one, not the stale cache.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_target_map(repo_root, {
        "products.aspose.com": {
            "platforms": {
                "cells/python-net": {"url": "https://products.aspose.com/cells/python-net/", "http_status": 200},
                "cells/python-java": {"url": "https://products.aspose.com/cells/python-java/", "http_status": 200},
            },
            "families": {},
        },
    })
    overrides_dir = repo_root / "data" / "backlinks"
    overrides_dir.mkdir(parents=True)
    (overrides_dir / "platform_canonical_overrides.yaml").write_text(
        "overrides:\n"
        "  cells/python:\n"
        "    target_platform: \"python-net\"\n"
        "    http_verified: true\n",
        encoding="utf-8",
    )
    rr.configure(repo_root=repo_root)
    result = rr._detect_enterprise_link("cells", "python")
    assert result["url"] == "https://products.aspose.com/cells/python-net/"
    assert result["relationship"] == "platform"
    assert result["public_platform"] == "Python"


def test_load_canonical_overrides_none_when_file_absent(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rr.configure(repo_root=repo_root)
    assert rr._load_canonical_overrides() is None


def test_load_canonical_overrides_none_when_malformed(tmp_path):
    repo_root = tmp_path / "repo"
    overrides_dir = repo_root / "data" / "backlinks"
    overrides_dir.mkdir(parents=True)
    (overrides_dir / "platform_canonical_overrides.yaml").write_text("not: [valid: yaml: at: all", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    assert rr._load_canonical_overrides() is None


# --- _detect_seo_keywords (TC-HARDEN-39, MT037, Twenty-Seventh incident) ------------------------


def _write_keywords_file(repo_root, family, entries):
    keywords_dir = repo_root / "keywords"
    keywords_dir.mkdir(exist_ok=True)
    (keywords_dir / f"{family}.json").write_text(json.dumps(entries), encoding="utf-8")


def test_detect_seo_keywords_selects_real_platform_entry(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_keywords_file(repo_root, "cells", [
        {
            "sourcePath": "content/products.aspose.org/en/cells/_index.md",
            "keywords": ["family-level phrase"],
        },
        {
            "sourcePath": "content/products.aspose.org/en/cells/java/_index.md",
            "keywords": ["platform-level phrase"],
        },
    ])
    rr.configure(repo_root=repo_root)
    result = rr._detect_seo_keywords("cells", "java")
    assert result == {
        "keywords": ["platform-level phrase"],
        "source_path": "content/products.aspose.org/en/cells/java/_index.md",
        "entry_found": True,
    }


def test_detect_seo_keywords_falls_back_to_family_entry(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_keywords_file(repo_root, "cells", [
        {
            "sourcePath": "content/products.aspose.org/en/cells/_index.md",
            "keywords": ["family-level phrase"],
        },
    ])
    rr.configure(repo_root=repo_root)
    result = rr._detect_seo_keywords("cells", "java")
    assert result["entry_found"] is True
    assert result["keywords"] == ["family-level phrase"]
    assert result["source_path"] == "content/products.aspose.org/en/cells/_index.md"


def test_detect_seo_keywords_absent_file_degrades_gracefully(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rr.configure(repo_root=repo_root)
    result = rr._detect_seo_keywords("cells", "java")
    assert result == {"keywords": [], "source_path": None, "entry_found": False}


def test_detect_seo_keywords_malformed_json_degrades_gracefully(tmp_path):
    repo_root = tmp_path / "repo"
    keywords_dir = repo_root / "keywords"
    keywords_dir.mkdir(parents=True)
    (keywords_dir / "cells.json").write_text("{not valid json", encoding="utf-8")
    rr.configure(repo_root=repo_root)
    result = rr._detect_seo_keywords("cells", "java")
    assert result == {"keywords": [], "source_path": None, "entry_found": False}


def test_detect_seo_keywords_no_matching_entry_degrades_gracefully(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_keywords_file(repo_root, "cells", [
        {
            "sourcePath": "content/products.aspose.org/en/cells/net/_index.md",
            "keywords": ["net phrase"],
        },
    ])
    rr.configure(repo_root=repo_root)
    result = rr._detect_seo_keywords("cells", "java")
    assert result == {"keywords": [], "source_path": None, "entry_found": False}


def test_detect_seo_keywords_never_confused_by_a_different_platforms_entry(tmp_path):
    # Cross-product-contamination guard, mirroring _detect_homepage_link's own analogous test.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_keywords_file(repo_root, "cells", [
        {
            "sourcePath": "content/products.aspose.org/en/cells/net/_index.md",
            "keywords": ["net-only phrase"],
        },
        {
            "sourcePath": "content/products.aspose.org/en/cells/java/_index.md",
            "keywords": ["java phrase"],
        },
    ])
    rr.configure(repo_root=repo_root)
    result = rr._detect_seo_keywords("cells", "java")
    assert result["keywords"] == ["java phrase"]


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

    manifest = rr.push("testfam", "testplat", run_id, dry_run=True, acting_model="Test Model X")
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


# --- F-02: push() commit trailer must come from the caller, never a hardcoded literal ------


def _advance_to_approved(repo_root, family="testfam", platform="testplat"):
    manifest = rr.start_run(family, platform)
    run_id = manifest["run_id"]
    rr.plan_run(family, platform, run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    rr.ingest_candidate(family, platform, run_id)
    rr.verify_examples(family, platform, run_id)
    rr.approve(family, platform, run_id, note="looks good")
    return run_id


def test_push_requires_a_real_acting_model(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-f02-a")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _advance_to_approved(repo_root)

    with pytest.raises(rr.ReadmeRefreshRunError, match="acting_model"):
        rr.push("testfam", "testplat", run_id, dry_run=True, acting_model="")

    with pytest.raises(rr.ReadmeRefreshRunError, match="acting_model"):
        rr.push("testfam", "testplat", run_id, dry_run=True, acting_model="   ")


def test_push_commit_trailer_uses_the_caller_supplied_acting_model_not_a_hardcoded_literal(
    tmp_path, monkeypatch,
):
    """F-02 regression: readme_refresh_run.py:3678 used to hardcode
    'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>' regardless of which model was
    actually running the push -- contradicting MT032's 'real acting model, never hardcoded'
    rule (the same rule invariant 5.9 already applies to the merge-time trailer). Proves two
    things: (1) the trailer reflects whatever the CALLER passes, not a fixed string, and
    (2) no literal legacy model name ('Claude Sonnet 5', 'Claude Sonnet 4.6' -- both found
    hardcoded elsewhere in this repo's own doc examples) survives in the real commit object."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-f02-b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _advance_to_approved(repo_root)

    distinctive_model = "Totally-Distinctive-Test-Model-9000"
    rr.push("testfam", "testplat", run_id, dry_run=True, acting_model=distinctive_model)
    receipt_path = rr._run_root("testfam", "testplat", run_id) / "push" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    work_dir = repo_root / "reports" / "readme_refresh_runs" / "_scratch" / f"testfam-testplat-{run_id}"
    commit_message = _run_git(["log", "-1", "--format=%B", receipt["commit_sha"]], work_dir)
    assert f"Co-Authored-By: {distinctive_model} <noreply@anthropic.com>" in commit_message
    assert "Claude Sonnet 5" not in commit_message
    assert "Claude Sonnet 4.6" not in commit_message


# --- TC-16 (readme-refresh-trackb-and-followon-2026-09-01): publication-authority classifier
# + push gate ---------------------------------------------------------------------------------


def _make_mirror_shaped_clone_cache(clone_cache_dir):
    """Reshapes an already-cloned repo (a real git repo with 1 normal commit on `main`) into
    a mirror-shaped one in place: >=2 orphan roots reachable via --all, and main's own tip is
    itself a fresh zero-parent root -- the exact live signature confirmed on font/python this
    session (HEAD has 0 parents; `git rev-list --max-parents=0 --all` shows 12 roots)."""
    _run_git(["checkout", "--orphan", "second-orphan-root"], clone_cache_dir)
    _run_git(["commit", "-q", "--allow-empty", "-m", "an unrelated orphan branch"], clone_cache_dir)
    _run_git(["checkout", "--orphan", "new-main-root"], clone_cache_dir)
    _run_git(["commit", "-q", "--allow-empty", "-m", "a fresh, unrelated root for main"], clone_cache_dir)
    _run_git(["branch", "-f", "main", "new-main-root"], clone_cache_dir)
    _run_git(["checkout", "main"], clone_cache_dir)
    _run_git(["branch", "-D", "new-main-root"], clone_cache_dir)


def test_classify_target_authority_canonical_for_a_normal_repo(tmp_path, monkeypatch):
    """A real repo with actual depth (HEAD has a genuine parent) -- the scratch fixture's own
    single-commit clone is too shallow to exercise the zero_parent_head=False path on its own
    (every fresh repo's first-ever commit is itself a zero-parent root), so a second real
    commit is added here to give `main` a genuine parent."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc16-a")
    repo_root, _ = _make_scratch_repo(tmp_path)
    clone_cache_dir = repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
    _run_git(["commit", "-q", "--allow-empty", "-m", "a real second commit"], clone_cache_dir)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    result = rr.classify_target_authority("testfam", "testplat")
    assert result["authority"] == "canonical"
    assert result["signals"]["zero_parent_head"] is False
    assert result["signals"]["orphan_root_count"] == 1


def test_classify_target_authority_mirror_when_both_structural_signals_agree(tmp_path, monkeypatch):
    """The real font/python signature: HEAD has 0 parents AND >=2 orphan roots. Confirmed live
    this session via `git log -1 --format=%P HEAD` (empty) and `git rev-list --max-parents=0
    --all | wc -l` (12) against the real font/python clone cache."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc16-b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    clone_cache_dir = repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
    _make_mirror_shaped_clone_cache(clone_cache_dir)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    result = rr.classify_target_authority("testfam", "testplat")
    assert result["authority"] == "mirror"
    assert result["signals"]["zero_parent_head"] is True
    assert result["signals"]["orphan_root_count"] >= 2


def test_classify_target_authority_canonical_when_only_one_signal_present(tmp_path, monkeypatch):
    """A zero-parent HEAD alone (a real repo's very first commit, e.g. right after a fresh
    `git init`, or -- exactly what the unmodified scratch fixture already naturally is --
    a repo with exactly one commit) must NOT alone trigger mirror: only 1 root exists, and
    this is completely normal for any brand-new real project. Both signals must agree
    (conservative in the safe direction: a false 'canonical' is the dangerous failure mode,
    not a false 'mirror')."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc16-c")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    result = rr.classify_target_authority("testfam", "testplat")
    assert result["authority"] == "canonical"
    assert result["signals"]["zero_parent_head"] is True
    assert result["signals"]["orphan_root_count"] == 1


def test_push_refuses_on_mirror_target_without_acknowledgment(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc16-d")
    repo_root, _ = _make_scratch_repo(tmp_path)
    clone_cache_dir = repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
    _make_mirror_shaped_clone_cache(clone_cache_dir)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _advance_to_approved(repo_root)

    with pytest.raises(rr.ReadmeRefreshRunError, match="MIRROR"):
        rr.push("testfam", "testplat", run_id, dry_run=True, acting_model="Test Model")


def test_push_proceeds_on_mirror_target_with_explicit_acknowledgment(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc16-e")
    repo_root, _ = _make_scratch_repo(tmp_path)
    clone_cache_dir = repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
    _make_mirror_shaped_clone_cache(clone_cache_dir)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _advance_to_approved(repo_root)

    manifest = rr.push(
        "testfam", "testplat", run_id, dry_run=True, acting_model="Test Model",
        acknowledge_mirror_target="deliberate, reviewed test exception",
    )
    assert manifest["state"] == "APPROVED"  # dry-run rehearses back to APPROVED, per push()'s own contract
    receipt_path = rr._run_root("testfam", "testplat", run_id) / "push" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["target_authority"] == "mirror"
    assert receipt["acknowledge_mirror_target"] == "deliberate, reviewed test exception"


def test_push_on_canonical_target_never_requires_acknowledgment(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc16-f")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _advance_to_approved(repo_root)

    manifest = rr.push("testfam", "testplat", run_id, dry_run=True, acting_model="Test Model")
    assert manifest["state"] == "APPROVED"
    receipt_path = rr._run_root("testfam", "testplat", run_id) / "push" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["target_authority"] == "canonical"
    assert "acknowledge_mirror_target" not in receipt


# --- TC-27 (MT061-2026-09-01-TRACKB-FOLLOWON-2): publication status structurally separated
# from push() -- per phase6b-production-hardening-design.md S3.VII ---------------------------


def test_push_success_does_not_record_publication_only_reconciler_does(tmp_path, monkeypatch):
    """Acceptance criterion for TC-27: an agent calling push() end-to-end -- including a REAL,
    non-dry-run PR-open (mocked `gh pr create`) -- must never cause
    data/readme_published_state.json to gain or change a 'published' entry. Only a separate,
    subsequent reconcile-publications --apply call (publication_reconciler.apply_reconciliation,
    driven by a real, externally-confirmed PR merge event) may write it. This is the structural
    fix for the exact failure mode phase6b-production-hardening-design.md S3.VII names: an agent
    completing its own approval loop end-to-end -- push()'s old direct _record_publication()
    call, removed by this taskcard, used to do exactly that the moment `gh pr create` returned
    success, with zero verification anyone ever merged the PR.

    Uses the SAME product/PR context throughout: push() opens a real PR (against the local
    scratch 'upstream' repo standing in for GitHub) and its receipt's commit_sha/pr_url feed a
    synthetic reconciliation report, so the second half proves the reconciler -- not push() --
    is the only path that can turn that same PR into a 'published' record.
    """
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc27-a")
    monkeypatch.setenv("GH_TOKEN", "fake-token-for-local-push")
    repo_root, upstream_dir = _make_scratch_repo(tmp_path)

    # Pre-seed an unrelated product's row so this test also proves push() doesn't disturb
    # EXISTING registry state, not just that it fails to add a new one.
    published_state_path = repo_root / "data" / "readme_published_state.json"
    published_state_path.write_text(json.dumps({
        "schema_version": 1,
        "products": [{"family": "unrelated", "platform": "prod",
                      "last_known_publication": "2026-01-01", "evidence": "pre-existing row"}],
    }, indent=2), encoding="utf-8")
    before_state = published_state_path.read_text(encoding="utf-8")

    pr_url = "https://github.com/test-org/test-repo/pull/99"

    def _push_runner(cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess.run(cmd, **kwargs)
        if cmd[:2] == ["gh", "api"]:
            class _Result:
                returncode = 0
                stdout = json.dumps({
                    "permissions": {"push": True, "admin": False},
                    "default_branch": "main", "archived": False, "disabled": False,
                })
                stderr = ""
            return _Result()
        if cmd[:3] == ["gh", "pr", "create"]:
            class _Result:
                returncode = 0
                stdout = pr_url + "\n"
                stderr = ""
            return _Result()
        raise AssertionError(f"unexpected command in test: {cmd}")

    rr.configure(repo_root=repo_root, command_runner=_push_runner)
    run_id = _advance_to_approved(repo_root)

    manifest = rr.push("testfam", "testplat", run_id, dry_run=False, acting_model="Test Model TC-27")
    assert manifest["state"] == "PUSHED"
    receipt_path = rr._run_root("testfam", "testplat", run_id) / "push" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["dry_run"] is False
    assert receipt["pr_url"] == pr_url

    # The PR was genuinely opened against upstream -- the branch really exists there.
    branches_on_upstream = _run_git(["branch", "-a"], upstream_dir)
    assert receipt["branch"] in branches_on_upstream

    # Opening a PR IS still recorded in the external-action ledger ...
    ledger_path = repo_root / "reports" / "repo_presenter_actions.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert any(
        r["action"] == "readme_pr_opened" and r["details"]["pr_url"] == pr_url for r in rows
    )

    # ... but data/readme_published_state.json is completely untouched: byte-identical to
    # before push(), no row for testfam/testplat, and the old direct-write function is gone.
    after_state = published_state_path.read_text(encoding="utf-8")
    assert after_state == before_state
    state = json.loads(after_state)
    assert not any(
        row.get("family") == "testfam" and row.get("platform") == "testplat"
        for row in state["products"]
    )
    assert not hasattr(rr, "_record_publication")

    # Now prove the ONLY path that CAN write it: a real reconcile-publications --apply call
    # (publication_reconciler.apply_reconciliation), fed a report describing the exact same PR
    # push() just opened -- i.e. what TC-41's reconciler would discover after a real human
    # merge.
    def _reconciler_runner(cmd, **kwargs):
        if cmd[:2] == ["gh", "api"] and any("pulls/99" in part for part in cmd):
            class _Result:
                returncode = 0
                stdout = json.dumps({"merged_by": {"login": "babar-raza"}})
                stderr = ""
            return _Result()
        if cmd[:2] == ["gh", "api"] and any("contents/README.md" in part for part in cmd):
            class _Result:
                returncode = 0
                stdout = "# fake published content\n"
                stderr = ""
            return _Result()
        raise AssertionError(f"unexpected reconciler command in test: {cmd}")

    publication_reconciler.configure(repo_root=repo_root, command_runner=_reconciler_runner)
    try:
        report = {
            "family": "testfam", "platform": "testplat", "state": "UNRECORDED_PUBLICATION",
            "reason": "test-constructed: same PR push() just opened",
            "latest_readme_refresh_pr": {
                "number": 99, "url": pr_url,
                "merged_at": "2026-09-01T12:00:00Z",
                "merge_commit_sha": receipt["commit_sha"],
            },
            "registry_entry": None,
        }
        written = publication_reconciler.apply_reconciliation(report)
    finally:
        publication_reconciler.configure()  # reset so later tests aren't affected

    assert written is not None
    assert written["pr_number"] == 99
    assert written["reconciliation_state"] == "IN_SYNC"

    final_state = json.loads(published_state_path.read_text(encoding="utf-8"))
    row = next(
        r for r in final_state["products"]
        if r["family"] == "testfam" and r["platform"] == "testplat"
    )
    assert row["pr_number"] == 99
    assert "reconciled by publication_reconciler.py" in row["evidence"]
    # The pre-existing unrelated row survives untouched throughout.
    assert any(r["family"] == "unrelated" and r["platform"] == "prod" for r in final_state["products"])


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


def test_ingest_candidate_blocks_on_stale_java_package_import(tmp_path, monkeypatch):
    # Twenty-Fifth mission (2026-08-13): reproduces the real, live cells/java incident -- the
    # upstream repo renamed its Java package from com.aspose.cells_foss to org.aspose.cells_foss;
    # a candidate composed against a stale clone cache still imports the old package. Real
    # gate-firing proof through the actual CLI transition, not just the bare check function.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-025")
    repo_root, _ = _make_scratch_repo(tmp_path)
    clone_cache_dir = repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
    class_dir = clone_cache_dir / "src" / "main" / "java" / "org" / "aspose" / "cells_foss"
    class_dir.mkdir(parents=True)
    (class_dir / "Cell.java").write_text(
        "package org.aspose.cells_foss;\n\npublic class Cell {\n}\n", encoding="utf-8",
    )
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    stale_import_candidate = _GOOD_CANDIDATE.replace(
        "```python\nimport testproduct\n```",
        "```java\nimport com.aspose.cells_foss.Cell;\n```",
    )
    assert stale_import_candidate != _GOOD_CANDIDATE
    _write_candidate(repo_root, stale_import_candidate)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["code_example_imports_match_source"]["hard_gate"] is True
    findings = result["code_example_imports_match_source"]["findings"]
    assert any(f["class_name"] == "Cell" and f["reason"] == "wrong_package" for f in findings)

    # Fix it -- must then reach VERIFYING_EXAMPLES cleanly.
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"


def test_ingest_candidate_blocks_on_section_intro_meta_narration(tmp_path, monkeypatch):
    # MT046 (Thirty-Sixth incident, 2026-08-15 / TC-HARDEN-71): reproduces the real, live
    # font/python incident -- a Key Capabilities intro sentence narrating the document's own
    # editorial organization and leaking an internal source-file fact. Real gate-firing proof
    # through the actual CLI transition, not just the bare check function.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-046")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    narration_candidate = _GOOD_CANDIDATE.replace(
        "## Key Capabilities\n\n- Reads and writes TXT files.",
        "## Key Capabilities\n\n"
        "Here's what you get — a Capability Snapshot of why teams use it, grouped by real "
        "module rather than by workflow label. Highlights are both covered inline via "
        "backtick-quoted names below.\n\n"
        "- Reads and writes TXT files.",
    )
    assert narration_candidate != _GOOD_CANDIDATE
    _write_candidate(repo_root, narration_candidate)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["section_intro_no_meta_narration"]["hard_gate"] is True
    findings = result["section_intro_no_meta_narration"]["findings"]
    assert findings and findings[0]["section"] == "Key Capabilities"

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
        'pip install -e ".[dev]"\n```\n\n## Dependencies',
        'pip install -e ".[dev,extra]"\n```\n\n## Dependencies',
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
    # MT055/TC-MICRO-03: resolved dynamically, same reasoning as _write_candidate above.
    candidate_dir = rr._candidate_readme_path(family, platform).parent
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


# --- _readme_matches_published_upstream / readme_already_published bypass (TC-HARDEN-115, ------
# MT053, Forty-Fourth incident, 2026-08-18): once a candidate has already been pushed and
# merged upstream, the clone cache's own README.md becomes the candidate itself -- extracting
# "content to preserve" from it and cross-checking against a disposition file is a pure
# tautology, and the real, position-based unit_id extractors produce pure false-positive noise
# (confirmed live: 158 hard-gate failures for pdf/cpp before this gate existed). These tests
# prove the narrow detector fails closed in both directions, and that the 25 preservation-
# tracking result keys are uniformly, honestly skipped once published -- while a genuinely
# still-independent old README (the shared fixture's own default, unpublished state) is
# completely unaffected.


def test_readme_matches_published_upstream_true_for_identical_text():
    assert rr._readme_matches_published_upstream(_GOOD_CANDIDATE, _GOOD_CANDIDATE) is True


def test_readme_matches_published_upstream_true_for_whitespace_only_difference():
    padded = "\n\n" + _GOOD_CANDIDATE + "\n\n  \n"
    assert rr._readme_matches_published_upstream(padded, _GOOD_CANDIDATE) is True


def test_readme_matches_published_upstream_false_for_one_substantive_line_changed():
    changed = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.", "- Reads and writes CSV files.",
    )
    assert changed != _GOOD_CANDIDATE, "fixture construction must actually change one real line"
    assert rr._readme_matches_published_upstream(changed, _GOOD_CANDIDATE) is False


def test_readme_matches_published_upstream_false_for_genuinely_different_products():
    assert rr._readme_matches_published_upstream(_OLD_UPSTREAM_README, _GOOD_CANDIDATE) is False


def test_readme_matches_published_upstream_false_for_empty_inputs():
    assert rr._readme_matches_published_upstream("", _GOOD_CANDIDATE) is False
    assert rr._readme_matches_published_upstream(_GOOD_CANDIDATE, "") is False
    assert rr._readme_matches_published_upstream("", "") is False


_MT053_PRESERVATION_TRACKING_KEYS = (
    "content_unit_disposition_coverage",
    "content_unit_excerpt_matches_extraction",
    "content_unit_evidence_resolves",
    "content_unit_merged_into_target_section",
    "content_unit_no_exact_duplicate_merge",
    "content_unit_redundant_claim_verifiable",
    "content_unit_classification_plausibility",
    "content_unit_probable_duplicate",
    "content_unit_embedded_actionable_fact",
    "image_content_unit_excluded_reason_verified",
    "structural_unit_disposition_coverage",
    "structural_unit_evidence_resolves",
    "structural_unit_merged_into_target_section",
    "structural_unit_no_exact_duplicate_merge",
    "structural_unit_tree_paths_plausible",
    "code_example_disposition_coverage",
    "code_example_evidence_resolves",
    "code_example_no_exact_duplicate_merge",
    "code_example_api_coverage_survives",
    "code_example_excluded_reason_citation_too_narrow",
    "cli_category_representation",
    "badge_disposition_coverage",
    "badge_evidence_resolves",
    "badge_preserved_or_credited_in_candidate",
    "badge_probable_duplicate_disposition",
)


def test_run_deterministic_checks_bypasses_all_25_preservation_keys_once_published(tmp_path):
    repo_root, upstream_dir = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    # Publish: overwrite the clone cache's real README.md with the exact candidate text, so
    # old_readme_text IS the candidate (byte-identical, whitespace-normalized) -- the real,
    # confirmed shape of an already-merged product.
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    (clone_cache / "README.md").write_text(_GOOD_CANDIDATE, encoding="utf-8")
    # Deliberately no content-/structure-/code-example-/badge-dispositions.json written at all --
    # if the bypass didn't work, every disposition-coverage check would hard-fail on "no file".
    _write_candidate(
        repo_root, _GOOD_CANDIDATE, dispositions=[], structure_dispositions=[],
        badge_dispositions=[], code_example_dispositions=[],
    )

    result = rr._run_deterministic_checks("testfam", "testplat", _GOOD_CANDIDATE, clone_cache)

    assert result["readme_already_published"]["detail"]["published"] is True
    assert result["readme_already_published"]["hard_gate"] is False
    for key in _MT053_PRESERVATION_TRACKING_KEYS:
        entry = result[key]
        assert entry["findings"] == [], f"{key} must report zero findings once published"
        assert entry.get("skipped") is True, f"{key} must be marked skipped once published"
        assert "readme already matches the published upstream README" in entry["skip_reason"]


def test_run_deterministic_checks_leaves_unpublished_product_fully_unaffected(tmp_path):
    """Non-regression proof: a genuinely still-independent old README (this fixture's own
    default, unpublished state -- _OLD_UPSTREAM_README != _GOOD_CANDIDATE) must never trip the
    bypass, and every one of the 25 keys must behave exactly as it did before MT053 (real
    findings/hard_gate values, never the skipped shape)."""
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    assert (clone_cache / "README.md").read_text(encoding="utf-8") != _GOOD_CANDIDATE
    _write_candidate(repo_root, _GOOD_CANDIDATE)

    result = rr._run_deterministic_checks("testfam", "testplat", _GOOD_CANDIDATE, clone_cache)

    assert result["readme_already_published"]["detail"]["published"] is False
    for key in _MT053_PRESERVATION_TRACKING_KEYS:
        entry = result[key]
        assert "skipped" not in entry, f"{key} must not be skipped for a genuinely unpublished product"
        assert "skip_reason" not in entry


def test_project_structure_and_badge_candidate_checks_run_unconditionally_when_published(tmp_path):
    """The three candidate-quality checks that never read old_readme_text at all (project
    structure formatting, badge static-claims, no-duplicate-badges) must keep running
    regardless of published state -- confirmed by their absence from the skip set above and a
    direct re-run here."""
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    (clone_cache / "README.md").write_text(_GOOD_CANDIDATE, encoding="utf-8")
    _write_candidate(
        repo_root, _GOOD_CANDIDATE, dispositions=[], structure_dispositions=[],
        badge_dispositions=[], code_example_dispositions=[],
    )

    result = rr._run_deterministic_checks("testfam", "testplat", _GOOD_CANDIDATE, clone_cache)

    for key in ("project_structure_canonical_tree_format", "badge_static_claims_dynamic_fact",
                "no_duplicate_badges_in_candidate"):
        assert "skipped" not in result[key], f"{key} is a candidate-quality check, must never be skipped"


def test_audit_portfolio_surfaces_published_field_per_product(tmp_path, capsys):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    (clone_cache / "README.md").write_text(_GOOD_CANDIDATE, encoding="utf-8")
    _write_candidate(
        repo_root, _GOOD_CANDIDATE, dispositions=[], structure_dispositions=[],
        badge_dispositions=[], code_example_dispositions=[],
    )

    result = rr.audit_portfolio()
    assert result["products"][0]["published"] is True

    exit_code = rr.main(["audit-portfolio"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Already published upstream (1): testfam/testplat" in out


# --- TC-AUDIT-01: disposition_tracking must distinguish real verification from a
# published-status skip -- both report clean:true, but only one was ever actually checked
# (found live 2026-08-19: 5 of the portfolio's 8 "clean" products had never been composed at
# all, masked by this exact conflation) ------------------------------------------------------


def test_audit_portfolio_marks_real_verification_as_disposition_tracking_verified(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _write_candidate(repo_root, _GOOD_CANDIDATE)  # not published:true, real dispositions engaged and clean

    result = rr.audit_portfolio()
    product = result["products"][0]
    assert product["clean"] is True
    assert product["disposition_tracking"] == "verified"
    assert result["disposition_verified_count"] == 1


def test_audit_portfolio_marks_published_skip_as_disposition_tracking_skipped_published(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    (clone_cache / "README.md").write_text(_GOOD_CANDIDATE, encoding="utf-8")
    _write_candidate(
        repo_root, _GOOD_CANDIDATE, dispositions=[], structure_dispositions=[],
        badge_dispositions=[], code_example_dispositions=[],
    )

    result = rr.audit_portfolio()
    product = result["products"][0]
    assert product["published"] is True
    assert product["clean"] is True  # still reports clean:true -- the whole point of this gap
    assert product["disposition_tracking"] == "skipped_published"
    assert result["disposition_verified_count"] == 0  # NOT counted as real verification


def test_audit_portfolio_marks_real_findings_as_disposition_tracking_checked_dirty(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    _add_second_product(repo_root)
    _write_second_candidate(repo_root)  # known dirty: required_sections findings

    result = rr.audit_portfolio(family="testfam2", platform="testplat2")
    product = result["products"][0]
    assert product["clean"] is False
    assert product["disposition_tracking"] == "checked_dirty"
    assert result["disposition_verified_count"] == 0


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


# --- Thirty-First incident / MT041 (2026-08-14): dependency extraction BLOCKED -> recover ----


def test_plan_run_blocks_on_dependency_extraction_failure_and_recovers(tmp_path, monkeypatch):
    """Real, scratch-clone proof (mission regression test #10): a product with no registered
    ecosystem and no override entry makes plan_run raise ReadmeRefreshRunError, reusing the
    exact _block()/resume_state mechanism already proven at push()'s own call site -- no new
    BLOCKED sub-mechanism. Fixing the override and calling plan_run again (after recover)
    succeeds normally."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-mt041-a")
    repo_root, _ = _make_scratch_repo(tmp_path)
    # Remove the override this scratch repo normally carries for testfam/testplat, so real
    # extraction genuinely has nothing to fall back on.
    (repo_root / "data" / "dependency_overrides.json").write_text("{}", encoding="utf-8")
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    try:
        rr.plan_run("testfam", "testplat", run_id)
        assert False, "expected ReadmeRefreshRunError"
    except rr.ReadmeRefreshRunError as exc:
        assert "dependency extraction BLOCKED" in str(exc)

    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "BLOCKED"
    assert manifest["resume_state"] == "INPUTS_PINNED"

    # Fix it: restore a real override, recover, and confirm plan_run now succeeds.
    (repo_root / "data" / "dependency_overrides.json").write_text(json.dumps({
        "testfam/testplat": {
            "ecosystem": "pypi", "source_manifest_path": "pyproject.toml",
            "required": [{"name": "requests", "version_constraint": ">=2.0"}],
        },
    }), encoding="utf-8")
    manifest = rr.recover_run("testfam", "testplat", run_id, reason="dependency override restored")
    assert manifest["state"] == "INPUTS_PINNED"
    manifest = rr.plan_run("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"

    factpack_path = rr._run_root("testfam", "testplat", run_id) / "facts" / "factpack.json"
    factpack = json.loads(factpack_path.read_text(encoding="utf-8"))
    assert {e["name"] for e in factpack["dependencies"]["required"]} == {"requests"}


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


# --- TC-26 (readme-refresh-trackb-and-followon-2026-09-01): UPSTREAM-BROKEN classification --
#
# Confirmed live and load-bearing against the real tex/python clone cache: 102 of 119 real
# source files fail ast.parse (genuine pre-existing IndentationError). `pip install -e`
# succeeds regardless (setuptools never compiles every file at install time) -- the failure
# only surfaces at real IMPORT time, with `aspose_tex/_input/catcode.py:66:
# IndentationError: expected an indented block after 'for' statement on line 65` as the
# traceback's own last frame, never the verification script itself.


def test_classify_python_failure_upstream_broken_real_syntax_error_in_dependency(tmp_path):
    script_path = tmp_path / "block_0.py"
    # A real Python traceback shape: importing a broken dependency module.
    traceback_text = (
        'Traceback (most recent call last):\n'
        f'  File "{script_path}", line 1, in <module>\n'
        '    import broken_pkg\n'
        '  File "C:\\clone_cache\\broken_pkg\\__init__.py", line 3, in <module>\n'
        '    from broken_pkg.inner import thing\n'
        '  File "C:\\clone_cache\\broken_pkg\\inner.py", line 66\n'
        '    table[c] = X\n'
        '    ^^^^^\n'
        "IndentationError: expected an indented block after 'for' statement on line 65\n"
    )
    reason, detail = rr._classify_python_failure(traceback_text, script_path)
    assert reason == "UPSTREAM-BROKEN"
    assert "inner.py" in detail
    assert "IndentationError" in detail


def test_classify_python_failure_stays_runtime_error_for_the_blocks_own_defect(tmp_path):
    script_path = tmp_path / "block_0.py"
    # A real AttributeError from the READER's own example misusing a real, working API --
    # must never be misattributed to upstream.
    traceback_text = (
        'Traceback (most recent call last):\n'
        f'  File "{script_path}", line 3, in <module>\n'
        '    workbook.doesnt_exist()\n'
        "AttributeError: 'Workbook' object has no attribute 'doesnt_exist'\n"
    )
    reason, detail = rr._classify_python_failure(traceback_text, script_path)
    assert reason == "RUNTIME-ERROR"
    assert "doesnt_exist" in detail


def test_classify_python_failure_syntax_error_in_the_block_itself_stays_runtime_error(tmp_path):
    """A syntax error whose LAST frame IS the block's own script (the reader's own example
    has a real typo) is the reader's fault, not upstream's -- must stay RUNTIME-ERROR."""
    script_path = tmp_path / "block_0.py"
    traceback_text = (
        f'  File "{script_path}", line 2\n'
        '    if True\n'
        '          ^\n'
        'SyntaxError: expected \':\'\n'
    )
    reason, _detail = rr._classify_python_failure(traceback_text, script_path)
    assert reason == "RUNTIME-ERROR"


def test_run_single_python_block_upstream_broken_real_import_of_a_genuinely_broken_local_package(tmp_path, monkeypatch):
    """Fully real acquire->execute->classify, zero network dependency -- a real, minimal,
    locally-installable package with a genuine IndentationError in a submodule (the same
    real defect shape confirmed live on tex/python) stands in for the clone cache."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc26")
    clone_cache_root = tmp_path / "clone_cache_root"
    clone_cache = clone_cache_root / "aspose_testfam_testplat"
    pkg_dir = clone_cache / "brokenpkg"
    pkg_dir.mkdir(parents=True)
    (clone_cache / "setup.py").write_text(
        "from setuptools import setup, find_packages\n"
        "setup(name='brokenpkg_e2e', version='0.1', packages=find_packages())\n",
        encoding="utf-8",
    )
    (pkg_dir / "__init__.py").write_text("from brokenpkg.inner import VALUE\n", encoding="utf-8")
    # A real, genuine IndentationError -- not synthesized text, actual invalid Python.
    (pkg_dir / "inner.py").write_text("if True:\npass\nVALUE = 1\n", encoding="utf-8")
    rr.configure(clone_cache_root=clone_cache_root)

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    acquire = rr._acquire_python_environment(
        work_dir, {"published": False, "candidate": {"name": "doesnt-matter"}}, clone_cache,
    )
    assert acquire["ok"] is True, acquire["detail"]
    result = rr._run_single_python_block(acquire["venv_python"], "import brokenpkg\n", work_dir, 0)

    assert result["status"] == "BLOCKED-WITH-REASON"
    assert result["reason"] == "UPSTREAM-BROKEN", result
    assert "inner.py" in result["detail"]
    assert "IndentationError" in result["detail"]


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


# --- TC-25 (readme-refresh-trackb-and-followon-2026-09-01): typescript_verification_runner --
#
# Same established practice as python_verification_runner's own test header directly above:
# the network-dependent half (a real `npm install`) is deliberately NOT exercised in the
# committed suite, to keep it fast and network-independent. The acquire-failure and stub-
# classification paths below are fully real and network-independent. The full real acquire->
# tsc->tsx path was separately, manually proven end-to-end against a real product (cells/
# typescript) -- see this taskcard's own evidence_refs in taskcards.jsonl for the exact
# command and result.


def test_acquire_typescript_environment_no_clone_cache(tmp_path):
    result = rr._acquire_typescript_environment(tmp_path, tmp_path / "no-such-clone-cache")
    assert result["ok"] is False
    assert "no clone cache directory" in result["detail"]


def test_acquire_typescript_environment_no_package_json(tmp_path):
    clone_cache = tmp_path / "clone_cache"
    clone_cache.mkdir()
    (clone_cache / "README.md").write_text("# hi\n", encoding="utf-8")
    result = rr._acquire_typescript_environment(tmp_path, clone_cache)
    assert result["ok"] is False
    assert "no package.json" in result["detail"]


def test_typescript_verification_runner_non_typescript_blocks_stay_stub(tmp_path):
    candidate_path = tmp_path / "readme.md"
    candidate_path.write_text(
        "## Installation\n\n```bash\nnpm install\n```\n\n"
        "## Quick Start\n\n```csharp\nvar x = 1;\n```\n",
        encoding="utf-8",
    )
    result = rr.typescript_verification_runner(candidate_path, {"family": "testfam", "platform": "testplat"})
    assert result["runner"] == "typescript_verification_runner_v1"
    assert result["blocks_found"] == 2
    assert result["all_named"] is True
    assert all(b["status"] == "BLOCKED-WITH-REASON" and b["reason"] == "TOOLCHAIN-UNAVAILABLE"
               for b in result["block_statuses"])


def test_typescript_verification_runner_recognizes_both_typescript_and_ts_tags(tmp_path):
    """The candidate's own fenced-block language tag is `typescript` (see any real product's
    Quick Start section, e.g. cells/typescript), but the shared `ts`/`typescript` alias must
    both route to the real runner path, not just one spelling."""
    candidate_path = tmp_path / "readme.md"
    candidate_path.write_text(
        "## A\n\n```typescript\nconsole.log(1);\n```\n\n## B\n\n```ts\nconsole.log(2);\n```\n",
        encoding="utf-8",
    )
    result = rr.typescript_verification_runner(candidate_path, {"family": "nope", "platform": "nope"})
    # No real clone cache for "nope/nope" -- both fall through to the honest ACQUIRE-FAILED
    # path rather than TOOLCHAIN-UNAVAILABLE, proving both tags were recognized as TypeScript
    # (not silently left as an unrecognized-language stub).
    assert result["blocks_found"] == 2
    assert all(b["reason"] == "ACQUIRE-FAILED" for b in result["block_statuses"])


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


def test_approve_forces_replan_on_ee_target_registry_drift(tmp_path, monkeypatch):
    """TC-13 slice (readme-refresh-trackb-and-followon-2026-09-01): the real tex/python
    incident, reproduced end-to-end through the actual state machine -- a candidate is
    composed and reaches AWAITING_REVIEW, then data/aspose_com_targets.json is corrected
    underneath it (exactly what happened for real, 4 days after tex/python's compose), and
    approve() must now catch this (previously invisible -- only clone_cache_head was ever
    checked)."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc13")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    rr.ingest_candidate("testfam", "testplat", run_id)
    rr.verify_examples("testfam", "testplat", run_id)

    # Simulate the real incident: the EE target registry is "corrected" after compose,
    # clone cache untouched.
    targets_path = repo_root / "data" / "aspose_com_targets.json"
    targets = json.loads(targets_path.read_text(encoding="utf-8"))
    targets["targets"]["products.aspose.com"]["platforms"]["testfam/testplat"]["url"] = (
        "https://products.aspose.com/testfam/testplat-corrected/"
    )
    targets_path.write_text(json.dumps(targets), encoding="utf-8")

    with pytest.raises(rr.ReadmeRefreshRunError, match="aspose_com_targets.json"):
        rr.approve("testfam", "testplat", run_id, note="approving despite registry drift")

    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"  # forced back, never silently approved


def test_start_run_pins_full_input_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-tc13-b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    full_manifest = manifest["pinned_inputs"]["full_manifest"]
    assert full_manifest["clone_cache"]["commit"] is not None
    assert full_manifest["clone_cache"]["tree"] is not None
    assert full_manifest["enterprise_edition_target"]["entry"] is not None
    assert full_manifest["manifest_hash"]


# MT055/TC-MICRO-01 (2026-08-18): the 6 disposition/candidate path helpers used to hardcode the
# literal segment "repo-presenter" regardless of configure()'s own reports_root -- confirmed live
# during the MT054 preservation audit to silently resolve `configure(reports_root="reports/repo-
# presenter-regen-full")` to a nonexistent nested path. The fix adds a dedicated
# `candidate_tree_name` knob instead of deriving anything from reports_root's own path segment,
# specifically because _reports_root is also consumed by _run_root/_product_root/
# _product_lock_path for run-evidence/lock paths that have nothing to do with the candidate tree.

def test_configure_default_candidate_tree_name_is_regen_full():
    # MT055/TC-MICRO-03 (2026-08-18): a real, evidence-backed decision promoted
    # repo-presenter-regen-full to the default tree (see reports/_scratch/
    # mt055_tree_divergence_inventory.json) -- this test documents that decision directly,
    # replacing the earlier "default is unchanged" guard from TC-MICRO-01, which correctly
    # asserted the OLD default before this later, separate decision was made.
    rr.configure()
    assert rr._candidate_readme_path("testfam", "testplat") == (
        rr._reports_root / "repo-presenter-regen-full" / "testfam" / "testplat" / "readme.md"
    )
    assert rr._content_dispositions_path("testfam", "testplat") == (
        rr._reports_root / "repo-presenter-regen-full" / "testfam" / "testplat" / "content-dispositions.json"
    )
    assert rr._structure_dispositions_path("testfam", "testplat") == (
        rr._reports_root / "repo-presenter-regen-full" / "testfam" / "testplat" / "structure-dispositions.json"
    )
    assert rr._badge_dispositions_path("testfam", "testplat") == (
        rr._reports_root / "repo-presenter-regen-full" / "testfam" / "testplat" / "badge-dispositions.json"
    )
    assert rr._code_example_dispositions_path("testfam", "testplat") == (
        rr._reports_root / "repo-presenter-regen-full" / "testfam" / "testplat" / "code-example-dispositions.json"
    )
    assert rr._upstream_issues_path("testfam", "testplat") == (
        rr._reports_root / "repo-presenter-regen-full" / "testfam" / "testplat" / "upstream-issues.md"
    )


def test_configure_explicit_old_tree_name_still_addressable():
    # The old tree is not deleted or made unreachable -- it stays addressable by explicit name.
    rr.configure(candidate_tree_name="repo-presenter")
    assert rr._candidate_readme_path("testfam", "testplat") == (
        rr._reports_root / "repo-presenter" / "testfam" / "testplat" / "readme.md"
    )


def test_configure_candidate_tree_name_override_resolves_directly_no_nested_ghost_path(tmp_path):
    rr.configure(repo_root=tmp_path, candidate_tree_name="repo-presenter-regen-full")
    resolved = rr._content_dispositions_path("pdf", "go")
    expected = tmp_path / "reports" / "repo-presenter-regen-full" / "pdf" / "go" / "content-dispositions.json"
    assert resolved == expected
    # The historical bug's own exact shape: a nested "repo-presenter" segment must never appear.
    assert "repo-presenter" not in str(resolved.relative_to(tmp_path / "reports" / "repo-presenter-regen-full"))


def test_configure_candidate_tree_name_does_not_affect_run_evidence_or_lock_paths(tmp_path):
    rr.configure(repo_root=tmp_path, candidate_tree_name="repo-presenter-regen-full")
    # _run_root / _product_root / _product_lock_path must keep meaning "the real reports/ dir" --
    # they are not part of the candidate-tree concept this fix scopes to.
    assert rr._run_root("pdf", "go", "run-1") == tmp_path / "reports" / "readme_refresh_runs" / "pdf" / "go" / "run-1"
    assert rr._product_root("pdf", "go") == tmp_path / "reports" / "readme_refresh_runs" / "pdf" / "go"
    assert rr._product_lock_path("pdf", "go") == tmp_path / "reports" / "locks" / "readme_refresh" / "pdf-go.lock"


def test_configure_candidate_tree_name_real_pipeline_against_alternate_tree_no_copy_step(tmp_path, monkeypatch):
    """The real, end-to-end proof this fix exists for: ingest_candidate succeeds directly against
    a tree named differently from the default, with zero physical-copy isolated-mirror step --
    the exact workaround this fix makes unnecessary for any future audit."""
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-candidate-tree-name")
    repo_root, _upstream_dir = _make_scratch_repo(tmp_path)
    rr.configure(
        repo_root=repo_root, candidate_tree_name="alt-tree", command_runner=_fake_gh_command_runner(),
    )

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    candidate_dir = repo_root / "reports" / "alt-tree" / "testfam" / "testplat"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "readme.md").write_text(_GOOD_CANDIDATE, encoding="utf-8")
    (candidate_dir / "upstream-issues.md").write_text(_UPSTREAM_ISSUES_BLOCKING, encoding="utf-8")
    (candidate_dir / "content-dispositions.json").write_text(
        json.dumps(_CONTENT_DISPOSITIONS_FOR_SHARED_FIXTURE), encoding="utf-8"
    )
    (candidate_dir / "structure-dispositions.json").write_text(
        json.dumps(_STRUCTURE_DISPOSITIONS_FOR_SHARED_FIXTURE), encoding="utf-8"
    )
    (candidate_dir / "code-example-dispositions.json").write_text(
        json.dumps(_CODE_EXAMPLE_DISPOSITIONS_FOR_SHARED_FIXTURE), encoding="utf-8"
    )
    (candidate_dir / "badge-dispositions.json").write_text("[]", encoding="utf-8")

    rr.ingest_candidate("testfam", "testplat", run_id)  # must not raise -- no repo-presenter/ dir exists anywhere
    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"


# --- _write_candidate_verification_marker / _candidate_drift_findings ---------------------------
# readme-refresh-forensic-trust-audit-2026-08-25, Cluster H (rows 35/36): both traced to
# _write_candidate_verification_marker hashing Path.read_text()'s universal-newline-translated
# `text` instead of the file's real on-disk bytes (row 36), and audit_portfolio's run_id=None
# write unconditionally clobbering a prior bound run's provenance even when content is
# unchanged (row 35).


def _write_marker_test_candidate(repo_root, family, platform, raw_bytes):
    candidate_dir = repo_root / "reports" / rr._DEFAULT_CANDIDATE_TREE_NAME / family / platform
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "readme.md").write_bytes(raw_bytes)


def test_write_candidate_verification_marker_hashes_real_bytes_not_newline_translated_text(tmp_path):
    repo_root = tmp_path / "repo"
    raw_bytes = b"# Test\r\n\r\nCRLF-checked-out candidate.\r\n"
    candidate_dir = repo_root / "reports" / rr._DEFAULT_CANDIDATE_TREE_NAME / "testfam" / "testplat"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / "readme.md"
    candidate_path.write_bytes(raw_bytes)
    rr.configure(repo_root=repo_root)

    # Match every real call site exactly: `text = candidate_path.read_text(encoding="utf-8")`
    # performs universal-newline translation (CRLF -> LF), unlike a plain bytes.decode().
    translated_text = candidate_path.read_text(encoding="utf-8")
    assert translated_text != raw_bytes.decode("utf-8"), "fixture must actually exercise CRLF translation"
    rr._write_candidate_verification_marker("testfam", "testplat", translated_text, run_id="run-1")

    marker = rr._load_candidate_last_verified("testfam", "testplat")
    assert marker["readme_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert marker["readme_sha256"] != hashlib.sha256(translated_text.encode("utf-8")).hexdigest()


def test_candidate_drift_findings_no_false_positive_on_crlf_candidate(tmp_path):
    repo_root = tmp_path / "repo"
    raw_bytes = b"# Test\r\n\r\nCRLF-checked-out candidate.\r\n"
    _write_marker_test_candidate(repo_root, "testfam", "testplat", raw_bytes)
    rr.configure(repo_root=repo_root)

    rr._write_candidate_verification_marker(
        "testfam", "testplat", raw_bytes.decode("utf-8"), run_id="run-1"
    )
    # Content on disk has not changed since the marker was written -- must report no drift,
    # regardless of CRLF/LF normalization anywhere in the comparison.
    assert rr._candidate_drift_findings("testfam", "testplat") == []


def test_audit_only_marker_write_preserves_prior_run_id_when_content_unchanged(tmp_path):
    repo_root = tmp_path / "repo"
    raw_bytes = b"# Test\n\nUnchanged content.\n"
    _write_marker_test_candidate(repo_root, "testfam", "testplat", raw_bytes)
    rr.configure(repo_root=repo_root)

    text = raw_bytes.decode("utf-8")
    rr._write_candidate_verification_marker("testfam", "testplat", text, run_id="ingest-run-1")
    # An audit_portfolio-style call (run_id=None) re-confirming the SAME content must not
    # erase the prior bound run's provenance.
    rr._write_candidate_verification_marker("testfam", "testplat", text, run_id=None)

    marker = rr._load_candidate_last_verified("testfam", "testplat")
    assert marker["verified_by_run_id"] == "ingest-run-1"


def test_audit_only_marker_write_resets_run_id_when_content_changed(tmp_path):
    repo_root = tmp_path / "repo"
    raw_bytes = b"# Test\n\nOriginal content.\n"
    _write_marker_test_candidate(repo_root, "testfam", "testplat", raw_bytes)
    rr.configure(repo_root=repo_root)

    rr._write_candidate_verification_marker(
        "testfam", "testplat", raw_bytes.decode("utf-8"), run_id="ingest-run-1"
    )
    # Content genuinely changed since that bound run verified it -- no bound run has seen
    # this new content, so run_id must correctly reset to None, not inherit the stale value.
    new_bytes = b"# Test\n\nChanged content.\n"
    _write_marker_test_candidate(repo_root, "testfam", "testplat", new_bytes)
    rr._write_candidate_verification_marker(
        "testfam", "testplat", new_bytes.decode("utf-8"), run_id=None
    )

    marker = rr._load_candidate_last_verified("testfam", "testplat")
    assert marker["verified_by_run_id"] is None


# --- live_published_regression_portfolio (TC-17, MT061-2026-09-01-TRACKB-FOLLOWON-2) --------


def _write_published_state_row(repo_root, row):
    path = repo_root / "data" / "readme_published_state.json"
    path.write_text(json.dumps({"schema_version": 1, "products": [row]}, indent=2), encoding="utf-8")


def _fake_live_readme_content_runner(readme_content: "str | None"):
    """TC-17's own configure()-seam fake, matching test_publication_reconciler.py's
    _fake_gh_runner shape but scoped to only the one gh call shape
    fetch_current_readme_blob_sha256 makes (the no-ref contents/README.md fetch). AGENTS.md
    Section 16's tiered monkeypatch policy requires this configure()-seam form -- never
    monkeypatch.setattr on an internal module function directly."""
    def _runner(argv, *args, **kwargs):
        joined = " ".join(argv)
        if "contents/README.md" in joined:
            if readme_content is None:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not found")
            return subprocess.CompletedProcess(argv, 0, stdout=readme_content, stderr="")
        raise AssertionError(f"unexpected gh invocation in this test: {argv!r}")
    return _runner


def _configure_live_readme_fetch(repo_root, readme_content: "str | None") -> None:
    """Must run AFTER rr.configure(repo_root=...) -- that call itself resets
    publication_reconciler's command_runner back to real subprocess.run (it only forwards
    repo_root), so the fake command_runner has to be layered on top, same ordering
    test_push_success_does_not_record_publication_only_reconciler_does already establishes
    for this module pair."""
    publication_reconciler.configure(
        repo_root=repo_root, command_runner=_fake_live_readme_content_runner(readme_content),
    )


def test_live_published_regression_portfolio_requires_explicit_scope(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    with pytest.raises(rr.ReadmeRefreshRunError, match="requires --family/--platform or --all"):
        rr.live_published_regression_portfolio()


def test_live_published_regression_portfolio_rejects_both_scope_and_all(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root)
    with pytest.raises(rr.ReadmeRefreshRunError, match="not both"):
        rr.live_published_regression_portfolio(family="testfam", platform="testplat", all_products=True)


def test_live_published_regression_portfolio_no_recorded_fingerprint_no_network_call(tmp_path):
    """The expected, common state for most of the real portfolio right now (reconciled before
    TC-41 added fingerprint recording): no live gh call should even be attempted -- there is
    nothing to compare against. The fake runner raises AssertionError on ANY invocation, so a
    regression that started fetching unconditionally would fail this test loudly."""
    repo_root, _ = _make_scratch_repo(tmp_path)
    _write_published_state_row(repo_root, {
        "family": "testfam", "platform": "testplat",
        "evidence": "reconciled by publication_reconciler.py: PR #1 ...",
        "pr_number": 1,
    })
    rr.configure(repo_root=repo_root)

    def _must_not_be_called(argv, *args, **kwargs):
        raise AssertionError("must not fetch live blob when no fingerprint is recorded")

    publication_reconciler.configure(repo_root=repo_root, command_runner=_must_not_be_called)

    result = rr.live_published_regression_portfolio(family="testfam", platform="testplat")
    assert result["total"] == 1
    assert result["products_with_recorded_fingerprint"] == 0
    assert result["products_with_finding"] == 0
    assert result["products"][0]["checked"] is False
    assert result["products"][0]["findings"] == []


def test_live_published_regression_portfolio_clean_match_no_finding(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    live_content = "# Unchanged live README\n"
    recorded_sha = hashlib.sha256(live_content.encode("utf-8")).hexdigest()
    _write_published_state_row(repo_root, {
        "family": "testfam", "platform": "testplat",
        "published_blob_sha256": recorded_sha, "published_commit": "abc123",
        "last_reconciled_at": "2026-08-30T00:00:00Z",
    })
    rr.configure(repo_root=repo_root)
    _configure_live_readme_fetch(repo_root, live_content)

    result = rr.live_published_regression_portfolio(family="testfam", platform="testplat")
    assert result["products_with_recorded_fingerprint"] == 1
    assert result["products_with_finding"] == 0
    assert result["products"][0]["checked"] is True
    assert result["products"][0]["findings"] == []


def test_live_published_regression_portfolio_genuine_regression_detected(tmp_path):
    """Positive-path proof (TC-17 mandatory item 4), exercised through the full live-network
    orchestration wrapper, not just the pure check function: a synthetic fixture where the
    live blob genuinely changed after the fingerprint was recorded -- no real product in this
    portfolio currently has this shape, disclosed honestly rather than skipped."""
    repo_root, _ = _make_scratch_repo(tmp_path)
    old_content = "# README before drift\n"
    recorded_sha = hashlib.sha256(old_content.encode("utf-8")).hexdigest()
    _write_published_state_row(repo_root, {
        "family": "testfam", "platform": "testplat",
        "published_blob_sha256": recorded_sha, "published_commit": "abc123",
        "last_reconciled_at": "2026-08-30T00:00:00Z",
    })
    rr.configure(repo_root=repo_root)
    new_content = "# README genuinely changed live, out of band\n"
    _configure_live_readme_fetch(repo_root, new_content)

    result = rr.live_published_regression_portfolio(family="testfam", platform="testplat")
    assert result["products_with_finding"] == 1
    product = result["products"][0]
    assert product["checked"] is True
    assert len(product["findings"]) == 1
    assert product["findings"][0]["current_live_blob_sha256"] == hashlib.sha256(
        new_content.encode("utf-8")
    ).hexdigest()
    assert product["findings"][0]["recorded_published_blob_sha256"] == recorded_sha


def test_live_published_regression_portfolio_failed_fetch_is_unchecked_not_a_finding(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    _write_published_state_row(repo_root, {
        "family": "testfam", "platform": "testplat",
        "published_blob_sha256": "recorded-sha",
    })
    rr.configure(repo_root=repo_root)
    _configure_live_readme_fetch(repo_root, None)  # simulates a gh failure

    result = rr.live_published_regression_portfolio(family="testfam", platform="testplat")
    assert result["products_with_finding"] == 0
    assert result["products"][0]["checked"] is False


def test_live_published_regression_portfolio_all_scopes_to_active_non_excluded_products(tmp_path):
    repo_root, _ = _make_scratch_repo(tmp_path)
    _write_published_state_row(repo_root, {"family": "testfam", "platform": "testplat"})
    rr.configure(repo_root=repo_root)

    def _must_not_be_called(argv, *args, **kwargs):
        raise AssertionError("no fingerprint recorded -- must not fetch")

    publication_reconciler.configure(repo_root=repo_root, command_runner=_must_not_be_called)

    result = rr.live_published_regression_portfolio(all_products=True)
    assert result["total"] == 1  # only the one active product in the fixture's products.json
    assert result["products"][0]["family"] == "testfam"
    assert result["products"][0]["platform"] == "testplat"
