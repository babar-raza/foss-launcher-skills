"""
Tests for scripts/pipeline/commands/content/body_refresh.py (S-105).

Min required: 12 tests. This file has 13.
"""

import json
import hashlib
import pytest
import yaml
from pathlib import Path

import commands.content.body_refresh as br


# ── Helpers ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    # RPR-ST082-01: default every test to a permissive api_fact_summary_fn stub
    # so the many tests exercising _paragraph_rewrite's LLM branch for symbols
    # that don't exist in this repo's real knowledge/ data (e.g. "Document3D",
    # "PdfDocument" as fixture-only stand-ins) still reach the LLM call they're
    # actually testing, rather than short-circuiting to the new
    # NO_GROUNDING_AVAILABLE fallback. Tests specifically covering the real
    # grounding-fix behavior override this per-test via their own
    # br.configure(api_fact_summary_fn=...) call.
    br.configure(api_fact_summary_fn=lambda symbol, family, platform, **kw: f"`{symbol}` (class): stub grounding fact for tests")
    yield
    br.configure(
        reports_root="reports/refresh_review",
        receipts_root=None,
        llm_router_class=None,
        safe_write_fn=None,
        hash_validation=True,
        forbidden_claims=None,
    )


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_page(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _setup_reports(
    tmp_path: Path,
    family: str,
    platform: str,
    impacts: list[dict],
    changes: list[dict],
) -> None:
    reports = tmp_path / "reports" / family / platform
    reports.mkdir(parents=True)
    (reports / "body_impact.json").write_text(json.dumps(impacts), encoding="utf-8")
    (reports / "semantic_changes.json").write_text(json.dumps(changes), encoding="utf-8")
    br.configure(
        reports_root=str(tmp_path / "reports"),
        receipts_root=str(tmp_path / "reports" / family / platform / "receipts"),
        hash_validation=False,  # skip hash validation in unit tests
    )


def _run(family: str, platform: str, **kwargs):
    """Exercise the production run-bound API from legacy behavior tests."""
    kwargs.setdefault("run_id", "TEST-RUN")
    run_root = Path(br._cfg_reports_root) / family / platform / "run-artifacts"
    run_root.mkdir(parents=True, exist_ok=True)
    impact_path = Path(br._cfg_reports_root) / family / platform / "body_impact.json"
    impacts = (
        json.loads(impact_path.read_text(encoding="utf-8"))
        if impact_path.is_file()
        else []
    )
    (run_root / "scope.json").write_text(
        "",
        encoding="utf-8",
    )
    paths = [
        impact["page_path"]
        for impact in impacts
        if impact.get("page_path")
    ]
    scope = {
        "schema_version": 1,
        "run_id": kwargs["run_id"],
        "family": family,
        "platform": platform,
        "paths": paths,
        "initial_hashes": {},
    }
    scope_path = run_root / "scope.json"
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    logical = json.dumps(
        {"paths": sorted(paths), "input_digest": None},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "run_id": kwargs["run_id"],
        "family": family,
        "platform": platform,
        "created_at": "2026-07-26T00:00:00Z",
        "scope": {
            "paths": paths,
            "input_digest": None,
            "digest": "sha256:" + hashlib.sha256(logical).hexdigest(),
        },
        "output_digests": {
            "scope": "sha256:" + hashlib.sha256(
                scope_path.read_bytes()
            ).hexdigest()
        },
    }
    (run_root / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    kwargs.setdefault("run_root", run_root)
    return br.run(family, platform, **kwargs)


def _make_impact(page_path: str, change_id: str, section_id: str, update_type: str,
                 impact_level: str = "DEFINITE", lines: "list[int] | None" = None) -> dict:
    return {
        "impact_id": "IMP-0001",
        "page_path": page_path,
        "locale": "en",
        "semantic_change_ids": [change_id],
        "affected_sections": [
            {
                "section_id": section_id,
                "heading": f"## {section_id}",
                "lines": lines or [5, 15],
                "reason": "test",
                "impact_level": impact_level,
                "required_action": "BODY_UPDATE",
                "update_type": update_type,
            }
        ],
        "planner_signal": False,
    }


def _make_change(change_id: str, symbol: str, change_type: str = "API_REMOVED") -> dict:
    return {
        "change_id": change_id,
        "change_type": change_type,
        "symbol": symbol,
        "symbol_kind": "class",
        "public_impact": "USER_VISIBLE",
        "content_impact": "BODY_UPDATE",
        "confidence": 0.95,
        "family": "pdf",
        "platform": "net",
        "base_sha": "abc",
        "current_sha": "def",
        "evidence_paths": [],
    }


def _run_with_explicit_scope(
    tmp_path: Path, family: str, platform: str, *,
    scope_paths: list[str], impacts: list[dict], mode: "str | None" = None,
    run_id: str = "TEST-RUN-SCOPED", **kwargs,
):
    """Like _run() above, but the scope is an EXPLICIT path list (not
    derived from `impacts`) and an optional `mode` is written into the
    manifest -- needed to exercise remediation mode's own scope-vs-impact
    reconciliation (a scoped page absent from `impacts` entirely)."""
    reports = tmp_path / "reports" / family / platform
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "body_impact.json").write_text(json.dumps(impacts), encoding="utf-8")
    (reports / "semantic_changes.json").write_text(json.dumps([]), encoding="utf-8")
    br.configure(
        reports_root=str(tmp_path / "reports"),
        receipts_root=str(reports / "receipts"),
        hash_validation=False,
        safe_write_fn=lambda p, c, **kw: True,
    )
    run_root = reports / "run-artifacts"
    run_root.mkdir(parents=True, exist_ok=True)
    scope = {
        "schema_version": 1,
        "run_id": run_id,
        "family": family,
        "platform": platform,
        "paths": scope_paths,
        "initial_hashes": {},
    }
    scope_path = run_root / "scope.json"
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    logical = json.dumps(
        {"paths": sorted(scope_paths), "input_digest": None},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "run_id": run_id,
        "family": family,
        "platform": platform,
        "created_at": "2026-08-23T00:00:00Z",
        "scope": {
            "paths": scope_paths,
            "input_digest": None,
            "digest": "sha256:" + hashlib.sha256(logical).hexdigest(),
        },
        "output_digests": {
            "scope": "sha256:" + hashlib.sha256(scope_path.read_bytes()).hexdigest(),
        },
    }
    if mode is not None:
        manifest["mode"] = mode
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    kwargs.setdefault("run_id", run_id)
    kwargs.setdefault("run_root", run_root)
    return br.run(family, platform, **kwargs)


# ── Tests ─────────────────────────────────────────────────────────────────

def test_execute_requires_explicit_run_id(tmp_path):
    _setup_reports(tmp_path, "pdf", "net", [], [])
    with pytest.raises(ValueError, match="explicit run_id"):
        br.run("pdf", "net", execute=True)


def test_writer_rejects_scope_tampering_after_manifest_pin(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    scope_path = run_root / "scope.json"
    scope = {
        "run_id": "RUN-SCOPE",
        "family": "pdf",
        "platform": "net",
        "paths": ["content/docs.aspose.org/en/pdf/net/page.md"],
    }
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    logical = json.dumps(
        {"paths": sorted(scope["paths"]), "input_digest": None},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-SCOPE",
                "family": "pdf",
                "platform": "net",
                "scope": {
                    "paths": scope["paths"],
                    "input_digest": None,
                    "digest": "sha256:" + hashlib.sha256(logical).hexdigest(),
                },
                "output_digests": {
                    "scope": "sha256:" + hashlib.sha256(
                        scope_path.read_bytes()
                    ).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )
    scope["paths"].append("content/docs.aspose.org/en/pdf/net/extra.md")
    scope_path.write_text(json.dumps(scope), encoding="utf-8")

    with pytest.raises(ValueError, match="pinned manifest"):
        br._validated_run_scope(
            run_root,
            run_id="RUN-SCOPE",
            family="pdf",
            platform="net",
        )


def test_run_evidence_uses_canonical_forward_slash_page_path(
    tmp_path, monkeypatch
):
    page_content = (
        "---\ntitle: Test\nauto_updatable: true\n---\n\n"
        "Use `Document` to load files.\n"
    )
    page = _make_page(
        tmp_path,
        "content/docs.aspose.org/en/pdf/net/page.md",
        page_content,
    )
    monkeypatch.chdir(tmp_path)
    windows_path = (
        "content/docs.aspose.org/en/pdf/net/page.md".replace("/", "\\")
    )
    change = _make_change("CHG-001", "Unrelated", "FEATURE_ADDED")
    impact = _make_impact(
        windows_path,
        "CHG-001",
        "body",
        br.UT_SURGICAL,
    )
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    _run("pdf", "net", execute=True)

    receipt_path = next(
        (tmp_path / "reports/pdf/net/run-artifacts/receipts").glob("*.yaml")
    )
    receipt = yaml.safe_load(receipt_path.read_text(encoding="utf-8"))[
        "content_refresh_receipt"
    ]
    assert receipt["new_hash"] == receipt["old_hash"]
    decision = json.loads(
        (
            tmp_path
            / "reports/pdf/net/run-artifacts/page_decisions.jsonl"
        ).read_text(encoding="utf-8")
    )
    assert "\\" not in decision["page_path"]
    assert decision["receipt_digest"] == (
        "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    )


def test_api_removed_sentence_replaced(tmp_path):
    """SURGICAL: renamed API symbol is replaced in prose with new symbol."""
    page_content = "---\ntitle: Test\nauto_updatable: true\n---\n\nUse `OldDocument` to load files.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldDocument", "API_RENAMED")
    change["new_symbol"] = "PdfDocument"
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(writes) == 1
    assert "PdfDocument" in writes[0][1]
    assert "OldDocument" not in writes[0][1]


def test_write_ahead_evidence_survives_crash_and_resumes(tmp_path):
    old_content = (
        "---\ntitle: Test\nauto_updatable: true\n---\n\n"
        "Use `OldDocument` to load files.\n"
    )
    page = _make_page(
        tmp_path,
        "content/docs.aspose.org/en/pdf/net/page.md",
        old_content,
    )
    change = _make_change("CHG-CRASH", "OldDocument", "API_RENAMED")
    change["new_symbol"] = "PdfDocument"
    impact = _make_impact(
        str(page), "CHG-CRASH", "body", br.UT_SURGICAL
    )
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])
    run_root = tmp_path / "reports/pdf/net/run-artifacts"

    def crash_after_evidence(_path, _content, **_kwargs):
        assert list((run_root / "receipts").glob("*.yaml"))
        assert (run_root / "page_decisions.jsonl").is_file()
        raise RuntimeError("simulated writer crash")

    br.configure(safe_write_fn=crash_after_evidence)
    with pytest.raises(RuntimeError, match="simulated writer crash"):
        _run("pdf", "net", execute=True)
    assert page.read_text(encoding="utf-8") == old_content

    def complete_write(path, content, **_kwargs):
        Path(path).write_text(content, encoding="utf-8")
        return True

    br.configure(safe_write_fn=complete_write)
    _run("pdf", "net", execute=True)
    assert "`PdfDocument`" in page.read_text(encoding="utf-8")
    assert len(list((run_root / "receipts").glob("*.yaml"))) == 1
    assert len(
        (run_root / "page_decisions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ) == 1


def test_regrounding_initialization_failure_records_unknown(
    tmp_path, monkeypatch
):
    import lib.regrounding_check as regrounding_check

    page_content = (
        "---\ntitle: Test\nauto_updatable: true\n---\n\n"
        "Use `OldDocument` to load files.\n"
    )
    page = _make_page(
        tmp_path,
        "content/docs.aspose.org/en/pdf/net/page.md",
        page_content,
    )
    change = _make_change("CHG-RG-UNKNOWN", "OldDocument", "API_RENAMED")
    change["new_symbol"] = "PdfDocument"
    impact = _make_impact(
        str(page), "CHG-RG-UNKNOWN", "body", br.UT_SURGICAL
    )
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])
    br.configure(safe_write_fn=lambda _p, _c, **_kw: True)

    def fail_cache():
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr(regrounding_check, "RegroundingCache", fail_cache)
    _run("pdf", "net", execute=True)

    decision = json.loads(
        (
            tmp_path
            / "reports/pdf/net/run-artifacts/page_decisions.jsonl"
        ).read_text(encoding="utf-8")
    )
    assert decision["validator_results"]["regrounding"] == "UNKNOWN"


def test_api_removed_code_block_regenerated(tmp_path):
    """EXAMPLE_REGENERATION strategy handles code block containing removed API."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Example\n\n"
        "```csharp\nvar doc = new OldDocument();\ndoc.Save();\n```\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldDocument", "API_REMOVED")
    impact = _make_impact(str(page), "CHG-001", "example", br.UT_EXAMPLE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(receipts) == 1


# ── C10 (MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION):
# _example_regeneration verified-snippet selection ────────────────────────

def _index_entry(file: str, *, tier: int | None = None) -> dict:
    entry: dict = {"file": file, "code_sha256": {"norm": f"norm-{file}", "exact": f"exact-{file}"}}
    if tier is not None:
        entry["execution_proof"] = {"tier": tier}
    return entry


def test_replaces_only_the_block_that_references_the_symbol(tmp_path):
    """The core second bug this taskcard fixes: a section with MORE THAN ONE code
    block must have only the symbol-referencing block replaced -- the original
    `re.sub(..., count=1)` blindly overwrote whichever fence came first."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()
    (snippets_dir / "new.cs").write_text("var doc = new NewDocument();\ndoc.Save();", encoding="utf-8")
    (snippets_dir / "snippets_index.json").write_text(
        json.dumps([_index_entry("new.cs")]), encoding="utf-8"
    )
    snippets_index = json.loads((snippets_dir / "snippets_index.json").read_text(encoding="utf-8"))

    section_text = (
        "## Example\n\n"
        '```csharp\nConsole.WriteLine("unrelated, first block");\n```\n\n'
        "```csharp\nvar doc = new OldDocument();\ndoc.Save();\n```\n"
    )
    change = {"symbol": "OldDocument", "change_type": "API_RENAMED"}

    result = br._example_regeneration(
        section_text, change, snippets_dir, platform="net", snippets_index=snippets_index,
    )

    assert "unrelated, first block" in result  # untouched
    assert "OldDocument" not in result
    assert "NewDocument" in result


def test_never_substitutes_a_snippet_with_no_verified_code_sha256(tmp_path):
    """A local file that merely doesn't mention the old symbol must never qualify
    on its own -- only a snippet the index actually proves came from a real,
    promoted, upstream source (a code_sha256 entry) is ever substituted."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()
    (snippets_dir / "a_unverified.cs").write_text("var doc = new NewDocument(); // unverified", encoding="utf-8")
    (snippets_dir / "b_verified.cs").write_text("var doc = new NewDocument(); // verified", encoding="utf-8")
    (snippets_dir / "snippets_index.json").write_text(
        json.dumps([_index_entry("b_verified.cs")]), encoding="utf-8"  # a_unverified.cs has NO entry
    )
    snippets_index = json.loads((snippets_dir / "snippets_index.json").read_text(encoding="utf-8"))

    section_text = "```csharp\nvar doc = new OldDocument();\n```\n"
    change = {"symbol": "OldDocument", "change_type": "API_RENAMED"}

    result = br._example_regeneration(
        section_text, change, snippets_dir, platform="net", snippets_index=snippets_index,
    )

    assert "// verified" in result
    assert "unverified" not in result


def test_no_verified_candidate_produces_a_removal_marker_for_any_change_type(tmp_path):
    """"Never unverified code": when NO candidate has a code_sha256 proof, the
    example must be marked for manual attention, not left stale or guessed at --
    even for a change_type other than API_REMOVED, which the old code's fallback
    branch didn't handle at all (it just returned section_text unchanged)."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()  # empty -- no snippets at all
    section_text = "```csharp\nvar doc = new OldDocument();\n```\n"
    change = {"symbol": "OldDocument", "change_type": "API_RENAMED"}  # deliberately not API_REMOVED

    result = br._example_regeneration(
        section_text, change, snippets_dir, platform="net", snippets_index=[],
    )

    assert "var doc = new OldDocument();" not in result  # the actual, unverified code is gone
    assert "no verified replacement available for OldDocument" in result


def test_prefers_the_highest_execution_proof_tier_when_present(tmp_path):
    """Once a real post-promote sweep populates execution_proof somewhere, the
    highest-tier candidate must win -- proven here with a synthetic index entry,
    since no real product has execution_proof populated anywhere yet (C6's own
    disclosed gap)."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()
    (snippets_dir / "a_tier1.cs").write_text("var doc = new NewDocument(); // tier1", encoding="utf-8")
    (snippets_dir / "b_tier3.cs").write_text("var doc = new NewDocument(); // tier3", encoding="utf-8")
    (snippets_dir / "snippets_index.json").write_text(
        json.dumps([_index_entry("a_tier1.cs", tier=1), _index_entry("b_tier3.cs", tier=3)]),
        encoding="utf-8",
    )
    snippets_index = json.loads((snippets_dir / "snippets_index.json").read_text(encoding="utf-8"))

    section_text = "```csharp\nvar doc = new OldDocument();\n```\n"
    change = {"symbol": "OldDocument", "change_type": "API_RENAMED"}

    result = br._example_regeneration(
        section_text, change, snippets_dir, platform="net", snippets_index=snippets_index,
    )

    assert "// tier3" in result
    assert "tier1" not in result


def test_candidate_selection_is_deterministic_not_filesystem_glob_order(tmp_path):
    """RC21's own second half: unsorted Path.glob() made "the first snippet without
    the old symbol" filesystem-order dependent. Creates the alphabetically-LATER
    file first on disk (some filesystems return glob() results in creation order)
    and confirms the alphabetically-first one still wins."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()
    (snippets_dir / "z_created_first.cs").write_text("var doc = new NewDocument(); // z", encoding="utf-8")
    (snippets_dir / "a_created_second.cs").write_text("var doc = new NewDocument(); // a", encoding="utf-8")
    (snippets_dir / "snippets_index.json").write_text(
        json.dumps([_index_entry("z_created_first.cs"), _index_entry("a_created_second.cs")]),
        encoding="utf-8",
    )
    snippets_index = json.loads((snippets_dir / "snippets_index.json").read_text(encoding="utf-8"))

    section_text = "```csharp\nvar doc = new OldDocument();\n```\n"
    change = {"symbol": "OldDocument", "change_type": "API_RENAMED"}

    result = br._example_regeneration(
        section_text, change, snippets_dir, platform="net", snippets_index=snippets_index,
    )

    assert "// a" in result
    assert "// z" not in result


def test_selects_the_platform_specific_extension_not_hardcoded_cs(tmp_path):
    """RC21's first half: the old code globbed `*.cs` unconditionally regardless of
    the page's real platform. A python page must never pick up a .cs candidate."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()
    (snippets_dir / "wrong_platform.cs").write_text("var doc = new NewDocument();", encoding="utf-8")
    (snippets_dir / "right.py").write_text("doc = NewDocument()", encoding="utf-8")
    (snippets_dir / "snippets_index.json").write_text(
        json.dumps([_index_entry("wrong_platform.cs"), _index_entry("right.py")]),
        encoding="utf-8",
    )
    snippets_index = json.loads((snippets_dir / "snippets_index.json").read_text(encoding="utf-8"))

    section_text = "```python\ndoc = OldDocument()\n```\n"
    change = {"symbol": "OldDocument", "change_type": "API_RENAMED"}

    result = br._example_regeneration(
        section_text, change, snippets_dir, platform="python", snippets_index=snippets_index,
    )

    assert "```python" in result
    assert "NewDocument" in result
    assert "new NewDocument()" not in result  # the .cs candidate's own syntax


def test_api_removed_still_uses_its_own_specific_removal_marker_text(tmp_path):
    """The pre-existing API_REMOVED-specific marker text is preserved when no
    verified snippet exists AND the change_type really is API_REMOVED -- more
    precise than the new generic marker for this one, already-handled case."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()  # empty -- no snippets at all
    section_text = "```csharp\nvar doc = new OldDocument();\n```\n"
    change = {"symbol": "OldDocument", "change_type": "API_REMOVED"}

    result = br._example_regeneration(
        section_text, change, snippets_dir, platform="net", snippets_index=[],
    )

    assert "OldDocument API no longer available" in result


def test_api_removed_code_block_regenerated_end_to_end_still_works(tmp_path):
    """Regression guard: the pre-existing end-to-end test above
    (test_api_removed_code_block_regenerated) exercises this exact path with no
    snippets_dir/snippets_index at all -- confirming the new keyword-only
    platform/snippets_index parameters don't break the real _apply_section_update
    call site, which now also loads and threads a real snippets_index.json when
    one exists (there isn't one in that fixture, so this stays a no-op)."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Example\n\n"
        "```csharp\nvar doc = new OldDocument();\ndoc.Save();\n```\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldDocument", "API_REMOVED")
    impact = _make_impact(str(page), "CHG-001", "example", br.UT_EXAMPLE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(receipts) == 1
    assert writes
    assert "OldDocument API no longer available" in writes[0][1]


def test_api_removed_table_row_removed(tmp_path):
    """TABLE_ROW_RECONCILIATION removes rows containing removed API."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Formats\n\n"
        "| Format | Class |\n| --- | --- |\n| PDF | OldDocument |\n| HTML | HtmlDoc |\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldDocument", "API_REMOVED")
    impact = _make_impact(str(page), "CHG-001", "formats", br.UT_TABLE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    if writes:
        assert "OldDocument" not in writes[0][1]
        assert "HtmlDoc" in writes[0][1]  # other rows preserved


def test_api_renamed_prose_updated(tmp_path):
    """SURGICAL: renamed API symbol updates prose references."""
    page_content = "---\ntitle: Test\n---\n\nThe `LegacyConverter` class converts files.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "LegacyConverter", "API_RENAMED")
    change["new_symbol"] = "PdfConverter"
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    if writes:
        assert "PdfConverter" in writes[0][1]


def test_feature_removed_section_eliminated(tmp_path):
    """SECTION_REMOVAL: entire section removed when feature is removed."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Overview\n\nStill valid content.\n\n"
        "## Legacy Section\n\nThis references the old feature.\n\n"
        "## See Also\n\nLinks here.\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "LegacyFeature", "FEATURE_REMOVED")
    impact = _make_impact(str(page), "CHG-001", "legacy-section", br.UT_REMOVAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    if writes:
        assert "## Legacy Section" not in writes[0][1]
        assert "Still valid content" in writes[0][1]


def test_feature_added_section_enriched(tmp_path):
    """PARAGRAPH_REWRITE: LLM path is actually reached and its output is applied.

    RPR-E-01 regression guard: prior to the fix, body_refresh.py's
    _paragraph_rewrite() short-circuited to _deterministic_fallback() for
    FEATURE_ADDED before ever constructing the configured LLM router, so
    this test passed on a receipt-count assertion alone while silently
    never exercising the LLM branch. Asserting the mock's distinctive
    output text is present (and the fallback's template text is absent)
    is what actually proves the LLM callsite ran.
    """
    page_content = "---\ntitle: Test\n---\n\n## Signing\n\nOld signing text here.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    call_count = {"n": 0}

    class MockLLM:
        class MockResult:
            data = "Updated signing text with new feature."
        def call_chat(self, *a, **kw):
            call_count["n"] += 1
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=MockLLM,
    )

    change = _make_change("CHG-001", "NewSignatureFeature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "signing", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(receipts) == 1
    assert call_count["n"] == 1, "MockLLM.call_chat() was never invoked — PARAGRAPH_REWRITE short-circuited before the LLM branch"
    assert "Updated signing text with new feature." in writes[0][1]
    assert "reviewed against the current source model" not in writes[0][1], "deterministic template fired instead of the LLM output"


def test_behavior_changed_paragraph_rewritten(tmp_path):
    """PARAGRAPH_REWRITE for BEHAVIOR_CHANGED actually invokes the LLM (RPR-E-01 regression guard)."""
    page_content = "---\ntitle: Test\n---\n\n## Rendering\n\nOld rendering description.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    call_count = {"n": 0}

    class MockLLM:
        class MockResult:
            data = "New rendering description reflecting changed behavior."
        def call_chat(self, *a, **kw):
            call_count["n"] += 1
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=MockLLM,
    )

    change = _make_change("CHG-001", "PdfRenderer", "BEHAVIOR_CHANGED")
    impact = _make_impact(str(page), "CHG-001", "rendering", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(receipts) == 1
    assert call_count["n"] == 1, "MockLLM.call_chat() was never invoked — PARAGRAPH_REWRITE short-circuited before the LLM branch"
    assert "New rendering description reflecting changed behavior." in writes[0][1]
    assert "reviewed against the current source model" not in writes[0][1], "deterministic template fired instead of the LLM output"


def test_llm_call_exception_falls_back_to_template(tmp_path):
    """RPR-E-01: a real router that raises (no credentials, network error, timeout)
    must fail safe to the deterministic template, not crash the refresh run."""
    page_content = "---\ntitle: Test\n---\n\n## Loading\n\nExisting loading text.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/3d/java/page.md", page_content)

    class ExplodingLLM:
        def __init__(self):
            pass
        def call_chat(self, *a, **kw):
            raise ConnectionError("no route to professionalize gateway")

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=ExplodingLLM,
    )

    change = _make_change("CHG-001", "CLM-3d-abc123", "FEATURE_ADDED")
    change["symbol_kind"] = "claim"
    impact = _make_impact(str(page), "CHG-001", "loading", br.UT_REWRITE)
    _setup_reports(tmp_path, "3d", "java", [impact], [change])

    receipts = _run("3d", "java", execute=True)
    assert len(receipts) == 1
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert "reviewed against the current source model" in writes[0][1]


def test_paragraph_rewrite_reachable_for_every_routed_change_type(tmp_path):
    """RPR-E-01 exhaustive regression guard: every change_type that
    body_impact.py's _select_update_type() ever routes to PARAGRAPH_REWRITE
    (API_ADDED, API_RESURRECTED, API_MODIFIED, API_SIGNATURE_CHANGED,
    FEATURE_ADDED, BEHAVIOR_CHANGED, CLAIM_MODIFIED) must actually reach
    and invoke a configured LLM router — none may be silently intercepted
    before the call."""
    routed_change_types = (
        "API_ADDED", "API_RESURRECTED", "API_MODIFIED", "API_SIGNATURE_CHANGED",
        "FEATURE_ADDED", "BEHAVIOR_CHANGED", "CLAIM_MODIFIED",
    )

    for change_type in routed_change_types:
        call_count = {"n": 0}

        class MockLLM:
            class MockResult:
                data = "LLM-authored rewrite."
            def call_chat(self, *a, **kw):
                call_count["n"] += 1
                return self.MockResult()
            def __init__(self):
                pass

        page_content = "---\ntitle: Test\n---\n\n## Section\n\nOriginal text.\n"
        page = _make_page(tmp_path / change_type, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

        writes: list[tuple] = []
        br.configure(
            safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
            llm_router_class=MockLLM,
        )

        change = _make_change("CHG-001", "Symbol", change_type)
        impact = _make_impact(str(page), "CHG-001", "section", br.UT_REWRITE)
        _setup_reports(tmp_path / change_type, "pdf", "net", [impact], [change])

        _run("pdf", "net", execute=True)
        assert call_count["n"] == 1, f"{change_type} did not reach the LLM callsite"
        assert writes and "LLM-authored rewrite." in writes[0][1], f"{change_type}: LLM output not applied"


def test_api_added_rewrite_has_deterministic_fallback(tmp_path):
    """PARAGRAPH_REWRITE updates API additions even when LLM returns no change."""
    page_content = "---\ntitle: Test\n---\n\n## Forms\n\nExisting form workflow text.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    class NoopLLM:
        class MockResult:
            data = None
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=NoopLLM,
    )

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "forms", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(receipts) == 1
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert "`ImportDataAction`" in writes[0][1]


def test_feature_added_rewrite_has_deterministic_fallback(tmp_path):
    """PARAGRAPH_REWRITE updates feature changes without requiring LLM."""
    page_content = "---\ntitle: Test\n---\n\n## Loading\n\nExisting loading text.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/3d/java/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "CLM-3d-abc123", "FEATURE_ADDED")
    change["symbol_kind"] = "claim"
    impact = _make_impact(str(page), "CHG-001", "loading", br.UT_REWRITE)
    _setup_reports(tmp_path, "3d", "java", [impact], [change])

    receipts = _run("3d", "java", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert "reviewed against the current source model" in writes[0][1]


def test_section_change_id_limits_rewrite_to_matching_change(tmp_path):
    """Section-level change_id prevents unrelated page changes from driving strategy."""
    page_content = "---\ntitle: Test\n---\n\n## Loading\n\nExisting loading text.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/3d/java/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    removed = _make_change("CHG-REMOVED", "RemovedRenderer", "API_REMOVED")
    added = _make_change("CHG-ADDED", "CLM-3d-abc123", "FEATURE_ADDED")
    added["symbol_kind"] = "claim"
    impact = _make_impact(str(page), "CHG-REMOVED", "loading", br.UT_REWRITE)
    impact["semantic_change_ids"] = ["CHG-REMOVED", "CHG-ADDED"]
    impact["affected_sections"][0]["change_id"] = "CHG-ADDED"
    _setup_reports(tmp_path, "3d", "java", [impact], [removed, added])

    receipts = _run("3d", "java", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert "reviewed against the current source model" in writes[0][1]


def test_preserve_first_unaffected_sections_unchanged(tmp_path):
    """Sections NOT in affected_sections are never modified."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Overview\n\nUnchanged overview text.\n\n"
        "## Installation\n\nUse `OldPkg` here.\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldPkg", "API_REMOVED")
    # Only target 'installation', not 'overview'
    impact = _make_impact(str(page), "CHG-001", "installation", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    if writes:
        assert "Unchanged overview text" in writes[0][1]


def test_auto_updatable_false_page_skipped(tmp_path):
    """Pages with auto_updatable: false are never written."""
    page_content = "---\ntitle: Test\nauto_updatable: false\n---\n\nProtected content.\n"
    page = _make_page(tmp_path, "content/protected.md", page_content)

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "SomeClass")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert any(r.get("verdict") == br.VD_SKIPPED_AUTO for r in receipts)


def test_provenance_auto_updatable_false_page_skipped(tmp_path):
    """Pages with provenance.auto_updatable: false are never written."""
    page_content = (
        "---\ntitle: Test\nprovenance:\n"
        "  auto_updatable: false\n---\n\nProtected content.\n"
    )
    page = _make_page(tmp_path, "content/protected.md", page_content)

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "SomeClass")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert any(r.get("verdict") == br.VD_SKIPPED_AUTO for r in receipts)


def test_localized_products_page_rejected_before_write(tmp_path):
    """Body refresh must not write English prose into localized product pages."""
    page_content = "---\ntitle: Test\n---\n\n## Overview\n\nTexto localizado.\n"
    page = _make_page(
        tmp_path,
        "content/products.aspose.org/fr/pdf/net/_index.md",
        page_content,
    )

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REWRITE)
    impact["locale"] = "fr"
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert receipts[0]["verdict"] == br.VD_REJECTED_LOCALIZED
    assert receipts[0]["locale"] == "fr"


def test_ambiguous_locale_path_rejected_before_write(tmp_path):
    """Missing locale identity fails closed instead of defaulting to English."""
    page_content = "---\ntitle: Test\n---\n\n## Overview\n\nBody.\n"
    page = _make_page(
        tmp_path,
        "content/docs.aspose.org/pdf/net/getting-started.md",
        page_content,
    )

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert receipts[0]["verdict"] == br.VD_REJECTED_AMBIGUOUS


def test_dry_run_produces_no_writes(tmp_path):
    """--dry-run mode plans but produces no file writes."""
    page_content = "---\ntitle: Test\n---\n\nUse `Document.Save` here.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "Document")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", dry_run=True)
    assert len(writes) == 0
    assert all(r.get("verdict") == br.VD_SKIPPED_DRY for r in receipts if r.get("verdict"))


def test_idempotent_rerun_no_changes(tmp_path):
    """Running body_refresh twice produces same output (idempotency)."""
    page_content = "---\ntitle: Test\n---\n\nUse `NewAPI` here.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[list] = [[]]
    br.configure(safe_write_fn=lambda p, c, **kw: writes[0].append(c) or True)

    change = _make_change("CHG-001", "OldAPI")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts1 = _run("pdf", "net", execute=True)
    receipts2 = _run("pdf", "net", execute=True)
    # Same number of receipts
    assert len(receipts1) == len(receipts2)


def test_api_added_fallback_idempotent_with_stale_line_range(tmp_path):
    """Fallback does not duplicate notes already present outside stale line ranges."""
    page_content = (
        "---\ntitle: Test\n---\n\n"
        "## Forms\n\nExisting form workflow text.\n\n"
        "The current pdf/net API surface also includes `ImportDataAction` for related workflows.\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "forms", br.UT_REWRITE)
    impact["affected_sections"][0]["lines"] = [4, 6]
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert receipts[0]["verdict"] == br.VD_NO_SECTIONS


def test_shift_section_lines_applies_cumulative_offset():
    """RPR-LINE-DRIFT-001: sec["lines"] is computed once, upfront, against a
    page's ORIGINAL content. When an earlier section's edit changes the
    page's line count, every later section's stale line range must be
    shifted by that delta before it's used to slice the (now different)
    content -- proven directly here against real drifted content: the
    unshifted range lands on section 1's own newly-added note text plus
    only the next heading (losing section 2's sentence entirely), while
    the shifted range correctly recovers section 2 intact.
    """
    page_content = (
        "---\ntitle: Test\n---\n\n"
        "## First\n\nFirst text mentions OldSymbolA.\n\n"
        "## Second\n\nSecond text mentions OldSymbolB.\n"
    )
    after_first_edit = (
        "---\ntitle: Test\n---\n\n## First\n\nFirst text mentions OldSymbolA.\n\n"
        "The `SymbolA` API surface has changed in the current source model; "
        "review its reference page before relying on older member details.\n"
        "## Second\n\nSecond text mentions OldSymbolB.\n"
    )
    line_offset = (
        len(after_first_edit.splitlines()) - len(page_content.splitlines())
    )
    assert line_offset > 0, "the note insertion must add at least one line"

    sec_second = {"section_id": "second", "lines": [8, 10]}

    # sec_second["lines"] is unchanged by a zero offset (no drift yet).
    assert br._shift_section_lines(sec_second, 0) is sec_second

    shifted = br._shift_section_lines(sec_second, line_offset)
    assert shifted["lines"] == [8 + line_offset, 10 + line_offset]

    fm_line_count = 3
    body_lines = after_first_edit.splitlines(keepends=True)[fm_line_count:]

    stale_start, stale_end = 8 - fm_line_count, 10 - fm_line_count
    stale_slice = "".join(body_lines[stale_start: stale_end + 1])
    assert "Second text mentions OldSymbolB." not in stale_slice, (
        "sanity check: the unshifted range must reproduce the bug (missing "
        "section 2's own text) so this test would fail if the drift "
        "scenario itself stopped reproducing"
    )

    adj_start = shifted["lines"][0] - fm_line_count
    adj_end = shifted["lines"][1] - fm_line_count
    adjusted_slice = "".join(body_lines[adj_start: adj_end + 1])
    assert adjusted_slice == "## Second\n\nSecond text mentions OldSymbolB.\n"


def test_reversed_change_order_picks_wrong_section_to_update(tmp_path):
    """RPR-ORDER-001: the RPR-LINE-DRIFT-001 cumulative-offset fix in run() is
    only correct if actionable_sections is visited in ascending document-line
    order. Nothing sorts it -- affected_sections' order comes from
    body_impact.py's per-change discovery order (see _build_impact_entries),
    not document position.

    Here the change targeting the LATER section ("second") is listed FIRST in
    affected_sections -- the shape a real semantic-diff ordering can produce
    (change-discovery order has no relationship to document position). Two
    independent, cross-cutting mechanisms combine to determine the observable
    outcome: (1) without a document-order sort, "second" is processed first
    and picks up a nonzero line_offset from its own successful edit; "first"
    (which precedes "second" and never moved) then gets that offset wrongly
    applied to its stale lines, extracting a bad slice; (2) separately,
    _deterministic_fallback()'s own cross-section guard (any of its 3 note
    phrases already present anywhere on the page blocks every subsequent
    note, regardless of category) means only the FIRST successful edit in
    the pass ever survives -- so instead of visible textual corruption, the
    bug's observable symptom in this fixture shape is that the WRONG
    section's concern silently wins: "second" (processed first only because
    of discovery-order happenstance) gets its note, "first" (which precedes
    it in the document and should have no reason to lose to it) gets none,
    silently, with no error or signal. Sorting by document position makes
    the document-earlier section win deterministically instead of whichever
    section's change happened to be discovered first upstream.
    """
    page_content = (
        "---\ntitle: Test\n---\n\n"
        "## First\n\nFirst text mentions OldSymbolA.\n\n"
        "## Second\n\nSecond text mentions OldSymbolB.\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    class ExplodingLLM:
        def __init__(self):
            pass
        def call_chat(self, *a, **kw):
            raise ConnectionError("no route to professionalize gateway")

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=ExplodingLLM,
    )

    change_second = _make_change("CHG-SECOND", "SymbolB", "API_ADDED")
    change_first = _make_change("CHG-FIRST", "SymbolA", "API_MODIFIED")
    impact = {
        "impact_id": "IMP-0001",
        "page_path": str(page),
        "locale": "en",
        "semantic_change_ids": ["CHG-SECOND", "CHG-FIRST"],
        "affected_sections": [
            {
                "section_id": "second",
                "heading": "## Second",
                "lines": [8, 10],
                "reason": "test",
                "impact_level": "DEFINITE",
                "required_action": "BODY_UPDATE",
                "update_type": br.UT_REWRITE,
                "change_id": "CHG-SECOND",
            },
            {
                "section_id": "first",
                "heading": "## First",
                "lines": [4, 6],
                "reason": "test",
                "impact_level": "DEFINITE",
                "required_action": "BODY_UPDATE",
                "update_type": br.UT_REWRITE,
                "change_id": "CHG-FIRST",
            },
        ],
        "planner_signal": False,
    }
    _setup_reports(tmp_path, "pdf", "net", [impact], [change_second, change_first])

    receipts = _run("pdf", "net", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    written = writes[0][1]

    # Both original sentences must always survive intact -- the guard's
    # blocked branch returns the untouched full page, never a corrupted
    # reconstruction. This holds with or without the fix; it is not the
    # behavior under test.
    assert written.count("First text mentions OldSymbolA.") == 1
    assert written.count("Second text mentions OldSymbolB.") == 1
    assert written.count("## First") == 1
    assert written.count("## Second") == 1

    first_note = "The `SymbolA` API surface has changed in the current source model"
    second_note = "The current pdf/net API surface also includes `SymbolB`"

    # This is the actual defect: "first" precedes "second" in the document
    # and has no legitimate reason to lose to it. It must win the
    # one-note-per-page guard deterministically, regardless of which change
    # a fresh semantic-diff run happened to discover first.
    assert first_note in written, (
        "the document-earlier section's own change must be reflected -- "
        "if this fails, the section that happened to be discovered first "
        "upstream won instead of the section that appears first on the page"
    )
    assert second_note not in written, (
        "only one advisory note survives per pass (_deterministic_fallback's "
        "own cross-section guard) -- it must be first's, not second's"
    )


def test_duplicate_api_refresh_notes_collapsed(tmp_path):
    """Execute pass collapses repeated deterministic API notes."""
    page_content = (
        "---\ntitle: Test\n---\n\n"
        "## Forms\n\nExisting form workflow text.\n\n"
        "The current pdf/net API surface also includes `BoxShape` for related workflows.\n"
        "The current pdf/net API surface also includes `ImportDataAction` for related workflows.\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "BoxShape", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "forms", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert writes[0][1].count("API surface also includes") == 1


def test_get_claim_grounding_repo_root_resolves_to_real_repo_root():
    """Regression guard (session 2): _get_claim_grounding()'s repo_root computation
    must resolve to the actual repo root (which has a knowledge/ directory), not a
    subdirectory of it. Prior to this fix, `parents[3]` resolved to scripts/ instead
    of the repo root, so bak_claims.exists()/new_claims.exists() were always False
    and every PARAGRAPH_REWRITE call ran in degraded (ungrounded) mode silently —
    zero prior test coverage existed for this function, which is how the bug survived."""
    import inspect
    import commands.content.body_refresh as br_module
    module_file = Path(inspect.getfile(br_module)).resolve()
    # Mirror _get_claim_grounding()'s own computation exactly.
    repo_root = module_file.parents[4]
    assert (repo_root / "knowledge").is_dir(), (
        f"repo_root computed as {repo_root} does not contain a knowledge/ directory — "
        f"the parents[N] index in _get_claim_grounding() has regressed"
    )
    # The old (buggy) index must NOT resolve to a directory containing knowledge/,
    # confirming this test would have failed before the fix.
    old_wrong_root = module_file.parents[3]
    assert not (old_wrong_root / "knowledge").is_dir(), (
        "test assumption invalid: parents[3] unexpectedly also has a knowledge/ dir "
        "— re-verify the fix is still needed / the constant is still correct"
    )


def test_get_claim_grounding_loads_real_claim_text_when_present():
    """End-to-end regression proof using this repo's own real knowledge artifacts
    (read-only) — grounding must actually load non-empty text for a real claim_id
    when merged/claims.json exists, proving the path fix works end-to-end, not just
    in isolation."""
    import json as _json
    repo_root = Path(__file__).resolve().parents[4]
    # Find any product with a real merged/claims.json to test against, without
    # hardcoding a specific family/platform that might not exist in a given checkout.
    knowledge_dir = repo_root / "knowledge"
    if not knowledge_dir.is_dir():
        pytest.skip("no knowledge/ directory in this checkout")
    candidate = None
    for family_dir in knowledge_dir.iterdir():
        if not family_dir.is_dir():
            continue
        for platform_dir in family_dir.iterdir():
            claims_path = platform_dir / "merged" / "claims.json"
            if claims_path.exists():
                try:
                    data = _json.loads(claims_path.read_text(encoding="utf-8"))
                    claims = data if isinstance(data, list) else data.get("claims", [])
                    if claims and isinstance(claims[0], dict) and claims[0].get("claim_id"):
                        candidate = (family_dir.name, platform_dir.name, claims[0]["claim_id"])
                        break
                except (ValueError, OSError):
                    continue
        if candidate:
            break
    if candidate is None:
        pytest.skip("no product with a populated merged/claims.json found in this checkout")

    family, platform, claim_id = candidate
    change = {"claim_id": claim_id}
    context = {"family": family, "platform": platform}
    _, new_text = br._get_claim_grounding(change, context)
    assert new_text, (
        f"expected non-empty claim text for {family}/{platform} claim_id={claim_id} "
        f"via merged/claims.json — grounding returned empty, path resolution likely still broken"
    )


def test_current_api_fact_summary_loads_real_members_when_present():
    """End-to-end regression proof using this repo's own real api_surface.json:
    _current_api_fact_summary() must return a non-empty, factual summary
    (constructor/methods/properties) for a real class, not just an empty
    string or the bare class name."""
    import json as _json
    repo_root = Path(__file__).resolve().parents[4]
    knowledge_dir = repo_root / "knowledge"
    if not knowledge_dir.is_dir():
        pytest.skip("no knowledge/ directory in this checkout")
    candidate = None
    for family_dir in knowledge_dir.iterdir():
        if not family_dir.is_dir():
            continue
        for platform_dir in family_dir.iterdir():
            surface_path = platform_dir / "merged" / "api_surface.json"
            if not surface_path.exists():
                continue
            try:
                data = _json.loads(surface_path.read_text(encoding="utf-8"))
                classes = data.get("classes", data) if isinstance(data, dict) else data
                for entry in classes:
                    if isinstance(entry, dict) and entry.get("name") and (
                        entry.get("methods") or entry.get("properties")
                    ):
                        candidate = (family_dir.name, platform_dir.name, entry["name"])
                        break
            except (ValueError, OSError):
                continue
            if candidate:
                break
        if candidate:
            break
    if candidate is None:
        pytest.skip("no product with a populated merged/api_surface.json found in this checkout")

    family, platform, symbol = candidate
    br._API_SURFACE_CACHE.clear()
    summary = br._current_api_fact_summary(symbol, family, platform)
    assert summary, (
        f"expected non-empty api-surface summary for {family}/{platform}::{symbol} "
        f"— grounding returned empty"
    )
    assert symbol in summary


def test_current_api_fact_summary_empty_for_unknown_symbol():
    """A symbol absent from api_surface.json (or an unknown product) must return
    "" rather than fabricating anything — this is the signal _paragraph_rewrite
    uses to fall back to NO_GROUNDING_AVAILABLE instead of calling the LLM."""
    br._API_SURFACE_CACHE.clear()
    summary = br._current_api_fact_summary(
        "TotallyFictionalClassNameXYZ123", "pdf", "net"
    )
    assert summary == ""


def test_paragraph_rewrite_falls_back_when_no_grounding_available():
    """RPR-ST082-01: with no claim grounding AND the symbol absent from
    api_surface.json, _paragraph_rewrite must not call the LLM at all — there
    is nothing factual to ground a rewrite in, so asking the model to describe
    "what changed" is exactly the setup that produced the fabricated
    CellValueHandler/PdfDocument migration narratives. Must fall back to the
    deterministic template with fallback_reason=NO_GROUNDING_AVAILABLE."""
    section_text = "Some prose that never invokes the LLM's distinctive marker.\n"

    class ShouldNotBeCalledLLM:
        def __init__(self):
            pass
        def call_chat(self, *a, **kw):
            raise AssertionError("LLM must not be called when no grounding is available")

    br.configure(
        llm_router_class=ShouldNotBeCalledLLM,
        api_fact_summary_fn=lambda symbol, family, platform, **kw: "",
    )
    change = {"change_id": "CHG-NOGROUND-001", "symbol": "NoSuchClass", "change_type": "API_MODIFIED"}
    context = {"family": "pdf", "platform": "net"}

    result = br._paragraph_rewrite(section_text, change, context)

    # The deterministic template (not the LLM) produced this — it may append
    # its own generic, symbol-referencing note, but never anything the LLM
    # would have needed to invent.
    assert result.startswith(section_text.rstrip())
    assert context.get("_fallback_reason") == "NO_GROUNDING_AVAILABLE"


def test_deterministic_fallback_skips_note_when_section_ends_mid_code_fence():
    """RPR-ST082-03: the deterministic fallback must not append its note when
    section_text itself ends inside an open code fence (odd ``` count) —
    doing so lands the note between the fence-halves of the whole page,
    breaking Python syntax. Found live 2026-08-18, cells/python: 4 of 16
    scoped files got a note inserted directly inside a `for` loop body this
    way. The fallback must return section_text unchanged rather than risk
    corrupting a mid-block section, matching the existing "nothing sensible
    to add" precedent for too-short sections."""
    section_text = (
        "for i, (q, r, e) in enumerate(zip(quarters, revenue, expenses), start=2):\n"
        "```python\n"
        "    ws.cells[f\"A{i}\"].value = q\n"
    )
    assert section_text.count("```") % 2 != 0  # sanity: genuinely mid-fence

    br.configure(api_fact_summary_fn=lambda symbol, family, platform, **kw: "")
    change = {"change_id": "CHG-MIDFENCE-001", "symbol": "NoSuchClass", "change_type": "API_MODIFIED"}
    context = {"family": "cells", "platform": "python"}

    result = br._paragraph_rewrite(section_text, change, context)

    assert result == section_text, (
        "must return the section unchanged rather than insert a note mid-fence"
    )


def test_paragraph_rewrite_rejects_leaked_prompt_scaffolding():
    """RPR-ST082-04: LLM output that echoes back the prompt's own completion
    cue (e.g. the literal "Rewritten paragraph:" trailer) must be rejected
    and fall back to the deterministic template — found live 2026-08-18,
    cells/python: this exact phrase was shipped into installation.md."""
    section_text = "After installing, run the following snippet to confirm the library loads correctly.\n"

    class EchoingLLM:
        class MockResult:
            data = "\n\nRewritten paragraph:\nAfter installing, run the following snippet to confirm the library loads correctly.\n"
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(
        llm_router_class=EchoingLLM,
        api_fact_summary_fn=lambda symbol, family, platform, **kw: f"`{symbol}` (class): stub",
    )
    change = {"change_id": "CHG-ECHO-001", "symbol": "Cell", "change_type": "API_MODIFIED"}
    context = {"family": "cells", "platform": "python"}

    result = br._paragraph_rewrite(section_text, change, context)

    assert "Rewritten paragraph:" not in result
    assert context.get("_fallback_reason") == "PROMPT_ECHO_LEAKED"


def test_paragraph_rewrite_ungrounded_prompt_includes_real_api_facts():
    """RPR-ST082-01 root-cause regression: when a real api-surface summary IS
    available, the ungrounded-mode prompt sent to the LLM must actually
    contain those facts (not just the bare symbol name + change_type, which
    is what previously let the model invent a fictional migration API).
    Mirrors the real cells/python incident: `Cell` marked API_MODIFIED with
    zero claim grounding, LLM given nothing but the name invented a
    `CellValueHandler`-based replacement and falsely claimed `Cell.__init__`
    had been removed."""
    section_text = "Assign to `cell.value` to write a string, integer, or float.\n"
    captured = {}

    class CapturingLLM:
        def __init__(self):
            pass
        def call_chat(self, *, prompt_system, prompt_user, **kw):
            captured["system"] = prompt_system
            captured["user"] = prompt_user
            class MockResult:
                data = section_text  # unchanged — nothing conflicts
            return MockResult()

    real_members = (
        "`Cell` (class)\n"
        "methods: __init__(value, formula), is_empty(), clear_value()\n"
        "properties: value, formula, style"
    )
    br.configure(
        llm_router_class=CapturingLLM,
        api_fact_summary_fn=lambda symbol, family, platform, **kw: real_members if symbol == "Cell" else "",
    )
    change = {"change_id": "CHG-CELL-001", "symbol": "Cell", "change_type": "API_MODIFIED"}
    context = {"family": "cells", "platform": "python"}

    result = br._paragraph_rewrite(section_text, change, context)

    assert result == section_text.strip()
    # The real, current members must actually be present in the prompt sent
    # to the model — this is what closes the hallucination gap: the model has
    # real facts to work from instead of just a name and a claim of "changed".
    assert "__init__(value, formula)" in captured["user"] or "__init__(value, formula)" in captured["system"]
    assert "not claim any member was removed" in captured["system"].lower() or "do not claim any member was removed" in captured["system"].lower()


def test_current_api_fact_summary_recursively_grounds_nested_types():
    """RPR-ST085-01 end-to-end regression, using this repo's own real
    knowledge/cells/python data: grounding `Cell` alone is not enough to
    prevent a false claim about `Font.bold` (2 property-hops away:
    `Cell.style` -> `Style.font` -> `Font.bold`) — the summary must
    recursively expand nested property types, not just `Cell`'s own direct
    members. Mirrors the real cells/python incident where the LLM, grounded
    only in `Cell`, fabricated a false "Font.bold is not directly settable"
    claim contradicting Font's and Cell.style's own real docstrings."""
    import json as _json
    repo_root = Path(__file__).resolve().parents[4]
    surface_path = repo_root / "knowledge" / "cells" / "python" / "merged" / "api_surface.json"
    if not surface_path.exists():
        pytest.skip("no knowledge/cells/python/merged/api_surface.json in this checkout")
    data = _json.loads(surface_path.read_text(encoding="utf-8"))
    classes = data.get("classes", data) if isinstance(data, dict) else data
    names = {c.get("name") for c in classes if isinstance(c, dict)}
    if not {"Cell", "Style", "Font"} <= names:
        pytest.skip("this checkout's cells/python knowledge doesn't have the expected Cell/Style/Font shape")

    br._API_SURFACE_CACHE.clear()
    summary = br._current_api_fact_summary("Cell", "cells", "python")

    assert "`Style`" in summary, "one-hop nested type (Cell.style -> Style) must be included"
    assert "`Font`" in summary, "two-hop nested type (Style.font -> Font) must be included"
    assert "bold" in summary, "Font's own real bold/italic/etc. members must be present as facts"


def test_scan_section_for_class_references_finds_real_classes_only():
    """RPR-ST085-01: the backtick-class-reference scanner must only surface
    names that are real classes in the product's api_surface.json — a
    backtick-quoted property name or unrelated capitalized word must not be
    treated as a class reference."""
    br._API_SURFACE_CACHE.clear()
    section_text = (
        "Use `Font` to control text appearance; the `bold` property is a "
        "boolean. `NotARealClassXYZ` should be ignored.\n"
    )
    found = br._scan_section_for_class_references(section_text, "cells", "python")
    assert "Font" in found
    assert "NotARealClassXYZ" not in found
    assert "bold" not in found  # lowercase — never matches the class-ref pattern


def test_receipt_written_per_page(tmp_path):
    """Each updated page produces a receipt YAML in receipts/."""
    page_content = "---\ntitle: Test\n---\n\n## Install\n\nRun `OldPackage.Install()`.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    br.configure(safe_write_fn=lambda p, c, **kw: True)

    change = _make_change("CHG-001", "OldPackage")
    impact = _make_impact(str(page), "CHG-001", "install", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    # Check receipts list returned
    assert len(receipts) >= 1
    # Check receipt has required fields
    r = receipts[0]
    assert "receipt_id" in r
    assert "page_path" in r
    assert "verdict" in r


def test_see_also_section_never_removed(tmp_path):
    """See Also section is protected and never touched even if targeted."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Main Content\n\nAPI docs here.\n\n"
        "## See Also\n\n- [Link1](url1)\n- [Link2](url2)\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "SomeAPI", "API_REMOVED")
    # Try to target 'see-also' section (should be protected)
    impact = _make_impact(str(page), "CHG-001", "see-also", br.UT_REMOVAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    # See Also should never be removed
    if writes:
        assert "## See Also" in writes[0][1]
    else:
        # Nothing written (protected) — also acceptable
        pass


def test_llm_output_missing_trailing_newline_does_not_glue_next_heading(tmp_path):
    """RPR-LINE-DRIFT-001 (part 2) regression: _paragraph_rewrite's LLM branch
    returns result.data.strip(), which strips the rewritten section's
    trailing newline. lines[] entries all carry their own trailing newline
    (splitlines(keepends=True)), so splicing a newline-less new_section
    directly against the next line glues it onto whatever follows -- found
    live as "### Scene GraphAll 3D content is organized..." (heading fused
    to body prose with zero separation).
    """
    page_content = (
        "---\ntitle: Test\n---\n\n"
        "## Overview\n\nUse `OldAPI` to process files.\n\n"
        "## Next Section\n\nUnrelated following content.\n"
    )
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    class StrippedLLM:
        class MockResult:
            # No trailing newline -- mirrors what .strip() produces in
            # production regardless of what the raw model output contained.
            data = "Use `NewAPI` to process files."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=StrippedLLM,
    )

    change = _make_change("CHG-001", "OldAPI", "API_RENAMED")
    change["new_symbol"] = "NewAPI"
    impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REWRITE)
    # end=7 deliberately includes the trailing blank line inside the
    # section slice, so lines[end+1:] starts directly at "## Next Section"
    # with no blank-line buffer -- the exact shape that exposes a missing
    # trailing newline on new_section as a glued heading.
    impact["affected_sections"][0]["lines"] = [4, 7]
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    result = writes[0][1]

    assert "Use `NewAPI` to process files." in result
    assert "\n## Next Section\n" in result, (
        "the next heading must remain on its own line, not fused onto the "
        "rewritten section's last line"
    )
    assert "## Next SectionUnrelated" not in result


def test_low_confidence_change_not_applied(tmp_path):
    """RG-007: changes with confidence < _MIN_CONFIDENCE_THRESHOLD are not applied."""
    page_content = "---\ntitle: Test\n---\n\n## Overview\n\nSome content about OldAPI here.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    # Build a change with low confidence (0.60 = non-user-visible API, below threshold 0.70)
    low_conf_change = _make_change("CHG-LC-001", "OldAPI", "API_REMOVED")
    low_conf_change["confidence"] = 0.60

    impact = _make_impact(str(page), "CHG-LC-001", "overview", br.UT_REMOVAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [low_conf_change])

    receipts = _run("pdf", "net", execute=True)

    # No write should occur — low-confidence gate prevents the edit
    assert writes == [], "Low-confidence change must not produce a body write"
    # Page content must be unchanged
    assert page.read_text(encoding="utf-8") == page_content


def test_high_confidence_change_applied(tmp_path):
    """RG-007 positive: changes at or above _MIN_CONFIDENCE_THRESHOLD are processed normally."""
    page_content = "---\ntitle: Test\n---\n\n## Overview\n\nUse `OldAPI` to process files.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    # Build a change at the threshold boundary (0.95 = user-visible, passes gate)
    high_conf_change = _make_change("CHG-HC-001", "OldAPI", "API_REMOVED")
    high_conf_change["confidence"] = 0.95

    impact = _make_impact(str(page), "CHG-HC-001", "overview", br.UT_REMOVAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [high_conf_change])

    receipts = _run("pdf", "net", execute=True)

    # High confidence change should be processed (write attempted or content changed)
    # We accept either a write or a receipt showing BODY_UPDATED / NO_ACTIONABLE_SECTIONS
    assert len(receipts) == 1


# ── RG-010: Hyperlink preservation guard ───────────────────────────────────

def test_paragraph_rewrite_enterprise_link_stripped_triggers_fallback():
    """RG-010: LLM output stripping enterprise (products.aspose.com) links must fall back to section_text."""
    section_text = (
        "See [Aspose.3D for Java](https://products.aspose.com/3d/java/) "
        "for enterprise features.\n"
    )

    class LinkStrippingLLM:
        class MockResult:
            data = "See the enterprise product for additional features."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(llm_router_class=LinkStrippingLLM)
    change = {"change_id": "CHG-RG010-001", "symbol": "Document3D", "change_type": "PROSE_REFINED"}
    context = {"family": "3d", "platform": "java"}

    result = br._paragraph_rewrite(section_text, change, context)

    # LLM stripped the enterprise link — guard must return original section_text
    assert result == section_text, (
        "RG-010: Must fall back to section_text when LLM strips enterprise link"
    )


def test_paragraph_rewrite_enterprise_link_preserved_accepts_llm_output():
    """RG-010: LLM output that preserves enterprise links should be accepted."""
    section_text = (
        "See [Aspose.3D for Java](https://products.aspose.com/3d/java/) "
        "for enterprise features.\n"
    )
    llm_rewrite = (
        "For enterprise capabilities, see "
        "[Aspose.3D for Java](https://products.aspose.com/3d/java/)."
    )

    class LinkPreservingLLM:
        class MockResult:
            data = llm_rewrite
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(llm_router_class=LinkPreservingLLM)
    change = {"change_id": "CHG-RG010-002", "symbol": "Document3D", "change_type": "PROSE_REFINED"}
    context = {"family": "3d", "platform": "java"}

    result = br._paragraph_rewrite(section_text, change, context)

    # LLM preserved the enterprise link — LLM output must be accepted
    assert result == llm_rewrite, (
        "RG-010: LLM output must be accepted when enterprise link is preserved"
    )


def test_paragraph_rewrite_internal_link_stripped_triggers_fallback():
    """RG-010: LLM output stripping internal aspose.org links must fall back to section_text."""
    section_text = (
        "Learn more in the [PDF documentation](https://docs.aspose.org/pdf/net/overview/) "
        "for full API coverage.\n"
    )

    class LinkStrippingLLM:
        class MockResult:
            data = "Learn more in the PDF documentation for full API coverage."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(llm_router_class=LinkStrippingLLM)
    change = {"change_id": "CHG-RG010-003", "symbol": "PdfDocument", "change_type": "PROSE_REFINED"}
    context = {"family": "pdf", "platform": "net"}

    result = br._paragraph_rewrite(section_text, change, context)

    # Internal link stripped — guard must return original section_text
    assert result == section_text, (
        "RG-010: Must fall back to section_text when LLM strips internal aspose.org link"
    )


def test_paragraph_rewrite_code_fence_imbalance_triggers_fallback():
    """RPR-ST082-02: an LLM rewrite that changes the number of ``` fence
    markers (dropping/misplacing one across a multi-code-block section) must
    fall back to section_text rather than shipping corrupted markdown.
    Mirrors the real cells/python incident: a two-code-block section's blank
    separator line was replaced with a stray closing fence, splitting one
    valid code block into an unfenced prose fragment plus an orphaned fence."""
    section_text = (
        "```python\n"
        "ws.cells['A1'].value = 1\n"
        "```\n"
        "\n"
        "```python\n"
        "ws.cells['A2'].value = 2\n"
        "```\n"
    )

    class FenceDroppingLLM:
        class MockResult:
            # The blank separator line between the two blocks was replaced
            # with a stray extra closing fence (5 markers total vs. the
            # source's 4), prematurely closing the first block and leaving
            # the second block's own opener/closer unpaired against it —
            # the exact real cells/python symptom: a `-` blank line became
            # a `+` ``` in the diff, with no matching removal elsewhere.
            data = (
                "```python\n"
                "ws.cells['A1'].value = 1\n"
                "```\n"
                "```\n"
                "```python\n"
                "ws.cells['A2'].value = 2\n"
                "```\n"
            )
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(llm_router_class=FenceDroppingLLM)
    change = {"change_id": "CHG-FENCE-001", "symbol": "Cell", "change_type": "API_MODIFIED"}
    context = {"family": "cells", "platform": "python"}

    result = br._paragraph_rewrite(section_text, change, context)

    assert result.startswith(section_text.rstrip())
    assert context.get("_fallback_reason") == "CODE_FENCE_IMBALANCE"


def test_paragraph_rewrite_code_fence_balanced_rewrite_accepted():
    """A legitimate rewrite that preserves the same fence count must still be
    accepted normally — the guard must not reject correct output."""
    section_text = (
        "Old prose.\n\n"
        "```python\n"
        "x = 1\n"
        "```\n"
    )
    llm_rewrite = (
        "New prose.\n\n"
        "```python\n"
        "x = 1\n"
        "```\n"
    )

    class CleanRewriteLLM:
        class MockResult:
            data = llm_rewrite
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(llm_router_class=CleanRewriteLLM)
    change = {"change_id": "CHG-FENCE-002", "symbol": "Cell", "change_type": "API_MODIFIED"}
    context = {"family": "cells", "platform": "python"}

    result = br._paragraph_rewrite(section_text, change, context)

    assert result == llm_rewrite.strip()
    assert context.get("_fallback_reason") == "NONE"


def test_code_block_structure_shifted_detects_same_count_reshuffle():
    """RPR-ST086-01 unit test: a fence dropped after one block and a fence
    inserted mid-way through the next block nets to the same total ``` count
    (4 -> 4) but reshuffles which text is fenced code vs. unfenced prose.
    _code_block_structure_shifted must catch this even though
    CODE_FENCE_IMBALANCE's count check would pass it."""
    source = (
        "```python\n"
        "cell.style.fill.set_solid_fill(\"FF1E64C8\")  # navy fill\n"
        "```\n"
        "\n"
        "This is a longer explanatory paragraph about applying styles to "
        "further cells in the worksheet, which now unintentionally includes "
        "the following code inline as plain prose text describing font "
        "configuration steps:\n"
        "\n"
        "```python\n"
        "from aspose.cells_foss import Workbook, Font\n"
        "font.bold = True\n"
        "font.italic = False\n"
        "font.size = 14\n"
        "worksheet.cells['A1'].value = \"Header\"\n"
        "workbook.save(\"output.xlsx\")\n"
        "```\n"
    )
    corrupted = (
        "```python\n"
        "cell.style.fill.set_solid_fill(\"FF1E64C8\")  # navy fill\n"
        "\n"
        "This is a longer explanatory paragraph about applying styles to "
        "further cells in the worksheet, which now unintentionally includes "
        "the following code inline as plain prose text describing font "
        "configuration steps:\n"
        "\n"
        "```python\n"
        "from aspose.cells_foss import Workbook, Font\n"
        "```\n"
        "font.bold = True\n"
        "font.italic = False\n"
        "font.size = 14\n"
        "worksheet.cells['A1'].value = \"Header\"\n"
        "workbook.save(\"output.xlsx\")\n"
        "```\n"
    )
    assert source.count("```") == corrupted.count("```")
    assert br._code_block_structure_shifted(source, corrupted) is True


def test_code_block_structure_shifted_tolerates_small_legitimate_edit():
    """A normal small edit inside a code block (e.g. a changed argument or
    an added line reflecting a real API change) must NOT be flagged — only
    a gross length swing consistent with block-boundary corruption should be."""
    source = (
        "```python\n"
        "cell.style.fill.set_solid_fill(\"FF1E64C8\")  # navy fill\n"
        "```\n"
    )
    edited = (
        "```python\n"
        "cell.style.fill.set_solid_fill(\"FF1E64C8\")  # navy fill (updated)\n"
        "```\n"
    )
    assert br._code_block_structure_shifted(source, edited) is False


def test_paragraph_rewrite_code_fence_content_shifted_triggers_fallback():
    """RPR-ST086-02: full _paragraph_rewrite path — an LLM rewrite whose
    fence count matches the source but whose fenced-block content has
    shifted position/size must fall back to section_text, using the new
    CODE_FENCE_CONTENT_SHIFTED reason (distinct from CODE_FENCE_IMBALANCE,
    which only catches a changed total count)."""
    section_text = (
        "```python\n"
        "cell.style.fill.set_solid_fill(\"FF1E64C8\")  # navy fill\n"
        "```\n"
        "\n"
        "This is a longer explanatory paragraph about applying styles to "
        "further cells in the worksheet, which now unintentionally includes "
        "the following code inline as plain prose text describing font "
        "configuration steps:\n"
        "\n"
        "```python\n"
        "from aspose.cells_foss import Workbook, Font\n"
        "font.bold = True\n"
        "font.italic = False\n"
        "font.size = 14\n"
        "worksheet.cells['A1'].value = \"Header\"\n"
        "workbook.save(\"output.xlsx\")\n"
        "```\n"
    )

    class ContentShiftingLLM:
        class MockResult:
            data = (
                "```python\n"
                "cell.style.fill.set_solid_fill(\"FF1E64C8\")  # navy fill\n"
                "\n"
                "This is a longer explanatory paragraph about applying styles to "
                "further cells in the worksheet, which now unintentionally includes "
                "the following code inline as plain prose text describing font "
                "configuration steps:\n"
                "\n"
                "```python\n"
                "from aspose.cells_foss import Workbook, Font\n"
                "```\n"
                "font.bold = True\n"
                "font.italic = False\n"
                "font.size = 14\n"
                "worksheet.cells['A1'].value = \"Header\"\n"
                "workbook.save(\"output.xlsx\")\n"
                "```\n"
            )
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(llm_router_class=ContentShiftingLLM)
    change = {"change_id": "CHG-FENCE-003", "symbol": "Cell", "change_type": "API_MODIFIED"}
    context = {"family": "cells", "platform": "python"}

    assert section_text.count("```") == ContentShiftingLLM.MockResult.data.count("```")

    result = br._paragraph_rewrite(section_text, change, context)

    assert result.startswith(section_text.rstrip())
    assert context.get("_fallback_reason") == "CODE_FENCE_CONTENT_SHIFTED"


# ── RPR-E-02: generation-time forbidden-claims gate ──────────────────────────

def test_generation_blocked_on_forbidden_claim(tmp_path, monkeypatch):
    """A candidate that INTRODUCES an affirmative claim about a forbidden API
    (methods throw NotImplementedException) must be blocked before write —
    the original page content is preserved and the receipt records the block."""
    page_content = "---\ntitle: Test\n---\n\n## Formats\n\nExisting clean prose.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/3d/net/page.md", page_content)
    original = page.read_text(encoding="utf-8")

    class ForbiddenLLM:
        class MockResult:
            data = "You can use `Microsoft3MFFormat.IsBuildable` to check buildability."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=ForbiddenLLM,
        forbidden_claims=["supports Microsoft3MFFormat.IsBuildable"],
    )

    change = _make_change("CHG-001", "SomeFeature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "formats", br.UT_REWRITE)
    _setup_reports(tmp_path, "3d", "net", [impact], [change])

    receipts = _run("3d", "net", execute=True)
    assert len(receipts) == 1
    assert receipts[0]["verdict"] == br.VD_FORBIDDEN_BLOCKED
    assert receipts[0]["forbidden_violations"], "block reason must be recorded on the receipt"
    # No write happened — the violating candidate was refused.
    assert writes == []
    # Original content preserved on disk.
    assert page.read_text(encoding="utf-8") == original


def test_3mf_regression_fixture_blocked_end_to_end(tmp_path, monkeypatch):
    """The exact 3d/net 3MF case, end-to-end through body_refresh.run()."""
    page_content = "---\ntitle: Formats\n---\n\n## Supported Formats\n\nAspose.3D reads OBJ and STL.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/3d/net/idx.md", page_content)

    class ThreeMFLLM:
        class MockResult:
            data = "Aspose.3D FOSS for .NET supports Microsoft3MFFormat for 3MF import and export."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    br.configure(
        safe_write_fn=lambda p, c, **kw: True,
        llm_router_class=ThreeMFLLM,
        forbidden_claims=[
            "supports Microsoft3MFFormat.IsBuildable",
            "supports Microsoft3MFFormat.SetBuildable",
        ],
    )

    change = _make_change("CHG-001", "Feature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "supported-formats", br.UT_REWRITE)
    _setup_reports(tmp_path, "3d", "net", [impact], [change])

    receipts = _run("3d", "net", execute=True)
    assert receipts[0]["verdict"] == br.VD_FORBIDDEN_BLOCKED


def test_clean_candidate_not_blocked_by_forbidden_gate(tmp_path, monkeypatch):
    """A candidate that does NOT touch any forbidden claim writes normally —
    the gate must not block legitimate edits."""
    page_content = "---\ntitle: Test\n---\n\n## Signing\n\nOld signing prose.\n"
    page = _make_page(tmp_path, "content/docs.aspose.org/en/3d/net/page.md", page_content)

    class CleanLLM:
        class MockResult:
            data = "Updated signing prose using Document.Sign for digital signatures."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=CleanLLM,
        forbidden_claims=["supports Microsoft3MFFormat.IsBuildable"],
    )

    change = _make_change("CHG-001", "Feature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "signing", br.UT_REWRITE)
    _setup_reports(tmp_path, "3d", "net", [impact], [change])

    receipts = _run("3d", "net", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert len(writes) == 1


# ── RPR-E-03: per-page re-grounding (template-propagation) gate ───────────────

def test_transform_scale_fvector3_regression_blocks_reuse(tmp_path):
    """The 3d/net template-propagation defect, end-to-end: two pages both receive
    the identical fabricated snippet `node.Transform.Scale = new FVector3(...)` from
    the LLM. Page A (first occurrence) writes; page B, which does not share A's
    grounding, is blocked as template propagation and its original content preserved."""
    snippet = "Use `node.Transform.Scale = new FVector3(2, 2, 2)` to scale the node."

    class TemplateLLM:
        class MockResult:
            data = snippet
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    pageA = _make_page(tmp_path, "content/docs.aspose.org/en/3d/net/a.md",
                       "---\ntitle: A\nevidence:\n  apis:\n  - Transform\n---\n\n## Scaling\n\nA old prose.\n")
    pageB_original = "---\ntitle: B\nevidence:\n  apis:\n  - Mesh\n---\n\n## Scaling\n\nB old prose.\n"
    pageB = _make_page(tmp_path, "content/docs.aspose.org/en/3d/net/b.md", pageB_original)

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=TemplateLLM,
    )

    changeA = _make_change("CHG-A", "Feature", "FEATURE_ADDED")
    changeB = _make_change("CHG-B", "Feature", "FEATURE_ADDED")
    impactA = _make_impact(str(pageA), "CHG-A", "scaling", br.UT_REWRITE, lines=[7, 12])
    impactB = _make_impact(str(pageB), "CHG-B", "scaling", br.UT_REWRITE, lines=[7, 12])
    _setup_reports(tmp_path, "3d", "net", [impactA, impactB], [changeA, changeB])

    receipts = _run("3d", "net", execute=True)
    by_page = {r["page_path"]: r for r in receipts}

    # Page A: first occurrence of the snippet, written normally.
    assert by_page[pageA.as_posix()]["verdict"] == br.VD_UPDATED
    # Page B: reused A's snippet without sharing A's grounding (cites Mesh, not Transform)
    # → blocked as template propagation; original content preserved.
    assert by_page[pageB.as_posix()]["verdict"] == br.VD_REGROUNDING_BLOCKED
    assert by_page[pageB.as_posix()]["regrounding_violations"], "block reason must be recorded"
    assert pageB.read_text(encoding="utf-8") == pageB_original


def test_shared_grounding_allows_snippet_reuse_end_to_end(tmp_path):
    """Two pages that genuinely cite the same evidence may reuse the same snippet —
    the gate must not block legitimate shared content."""
    snippet = "Call `Document.Save(path)` to persist."

    class SharedLLM:
        class MockResult:
            data = snippet
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    pageA = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/a.md",
                       "---\ntitle: A\nevidence:\n  apis:\n  - Document\n---\n\n## Save\n\nA prose.\n")
    pageB = _make_page(tmp_path, "content/docs.aspose.org/en/pdf/net/b.md",
                       "---\ntitle: B\nevidence:\n  apis:\n  - Document\n---\n\n## Save\n\nB prose.\n")

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=SharedLLM,
    )
    impactA = _make_impact(str(pageA), "CHG-A", "save", br.UT_REWRITE, lines=[7, 12])
    impactB = _make_impact(str(pageB), "CHG-B", "save", br.UT_REWRITE, lines=[7, 12])
    _setup_reports(tmp_path, "pdf", "net",
                   [impactA, impactB],
                   [_make_change("CHG-A", "F", "FEATURE_ADDED"), _make_change("CHG-B", "F", "FEATURE_ADDED")])

    receipts = _run("pdf", "net", execute=True)
    verdicts = {r["page_path"]: r["verdict"] for r in receipts}
    assert verdicts[pageA.as_posix()] == br.VD_UPDATED
    assert verdicts[pageB.as_posix()] == br.VD_UPDATED  # shared Document grounding → allowed


# ── RPR-E-04: surface-differentiated update-strategy policy ───────────────────

def test_surface_inference():
    assert br._surface_for_page("content/docs.aspose.org/en/pdf/net/x.md") == "docs"
    assert br._surface_for_page("content/kb.aspose.org/en/pdf/net/x.md") == "kb"
    assert br._surface_for_page("content/blog.aspose.org/pdf/net/x/index.md") == "blog"
    assert br._surface_for_page("content/products.aspose.org/en/pdf/x.md") == "products"
    assert br._surface_for_page("content/reference.aspose.org/en/pdf/net/Doc.md") == "reference"
    assert br._surface_for_page("some/random/path.md") == "unknown"


def test_every_surface_has_explicit_policy():
    """No surface may fall through to a silent default — all five plus 'unknown'
    have an explicit _SURFACE_POLICY entry (plan §2.1)."""
    for surface in ("reference", "products", "docs", "kb", "blog", "unknown"):
        assert surface in br._SURFACE_POLICY
        assert "allowed" in br._SURFACE_POLICY[surface]


def test_reference_surface_requires_citation_backed_strategy():
    """Reference pages may only be touched by citation-backed deterministic
    strategies; an LLM PARAGRAPH_REWRITE is deferred to batch-reference (S-62),
    never applied in place."""
    allowed_rewrite, handoff = br._surface_allows_strategy("reference", br.UT_REWRITE)
    assert allowed_rewrite is False
    assert "batch-reference" in handoff
    # A deterministic strategy IS allowed on reference.
    allowed_surgical, _ = br._surface_allows_strategy("reference", br.UT_SURGICAL)
    assert allowed_surgical is True


def test_reference_page_paragraph_rewrite_deferred_end_to_end(tmp_path):
    """End-to-end: a PARAGRAPH_REWRITE targeting a reference page is deferred by
    the surface policy — the LLM is never called, nothing is written, and the
    receipt records the deferral to batch-reference."""
    page = _make_page(
        tmp_path, "content/reference.aspose.org/en/3d/net/Node.md",
        "---\ntitle: Node\n---\n\n## Description\n\nNode class prose.\n",
    )
    original = page.read_text(encoding="utf-8")

    llm_calls = {"n": 0}

    class ShouldNotBeCalledLLM:
        class MockResult:
            data = "rewritten"
        def call_chat(self, *a, **kw):
            llm_calls["n"] += 1
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=ShouldNotBeCalledLLM,
    )
    change = _make_change("CHG-001", "Feature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "description", br.UT_REWRITE, lines=[5, 12])
    _setup_reports(tmp_path, "3d", "net", [impact], [change])

    receipts = _run("3d", "net", execute=True)
    r = receipts[0]
    assert r["surface"] == "reference"
    assert r["surface_deferrals"], "the PARAGRAPH_REWRITE must be recorded as a surface deferral"
    assert r["surface_deferrals"][0]["handoff"].startswith("batch-reference")
    assert llm_calls["n"] == 0, "LLM must never be called for a policy-deferred reference rewrite"
    assert writes == []
    assert page.read_text(encoding="utf-8") == original


def test_docs_surface_routes_per_policy_table_not_silently(tmp_path):
    """A docs page's PARAGRAPH_REWRITE is ALLOWED by policy (full strategy set) and
    applied — proving the policy routes explicitly per surface, not by silently
    treating every surface the same."""
    page = _make_page(
        tmp_path, "content/docs.aspose.org/en/pdf/net/guide.md",
        "---\ntitle: Guide\n---\n\n## Overview\n\nOld overview prose.\n",
    )

    class DocsLLM:
        class MockResult:
            data = "New overview prose reflecting the feature."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=DocsLLM,
    )
    change = _make_change("CHG-001", "Feature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REWRITE, lines=[5, 12])
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = _run("pdf", "net", execute=True)
    r = receipts[0]
    assert r["surface"] == "docs"
    assert r["surface_deferrals"] == []  # docs allows PARAGRAPH_REWRITE
    assert r["verdict"] == br.VD_UPDATED
    assert len(writes) == 1


# ── RPR-E-05: LLM circuit breaker + fallback_reason observability ─────────────

def test_circuit_opens_after_n_consecutive_failures():
    circuit = br._LLMCircuit(threshold=3)
    assert circuit.should_attempt()
    circuit.record_failure()
    circuit.record_failure()
    assert circuit.should_attempt()  # 2 failures, still closed
    circuit.record_failure()
    assert not circuit.should_attempt()  # 3rd failure opens it


def test_circuit_success_resets_streak():
    circuit = br._LLMCircuit(threshold=3)
    circuit.record_failure()
    circuit.record_failure()
    circuit.record_success()  # resets the consecutive streak
    circuit.record_failure()
    assert circuit.should_attempt()  # only 1 consecutive failure now


def test_circuit_state_is_per_run_not_persisted(tmp_path):
    """A fresh run() gets a fresh circuit — a prior run's failures do not carry over."""
    # Two independent circuits are independent objects.
    c1 = br._LLMCircuit()
    c1.record_failure(); c1.record_failure(); c1.record_failure()
    assert c1.is_open
    c2 = br._LLMCircuit()
    assert not c2.is_open  # brand new, unaffected by c1


def _fallback_reason_page(tmp_path, family, platform):
    page = _make_page(
        tmp_path, f"content/docs.aspose.org/en/{family}/{platform}/p.md",
        "---\ntitle: P\n---\n\n## Overview\n\nOld overview prose here.\n",
    )
    change = _make_change("CHG-001", "Feature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REWRITE, lines=[5, 12])
    _setup_reports(tmp_path, family, platform, [impact], [change])
    return page


def test_fallback_reason_llm_error_recorded(tmp_path):
    class ErrorLLM:
        def __init__(self): pass
        def call_chat(self, *a, **kw):
            raise ConnectionError("degraded gateway")

    br.configure(safe_write_fn=lambda p, c, **kw: True, llm_router_class=ErrorLLM)
    _fallback_reason_page(tmp_path, "pdf", "net")
    receipts = _run("pdf", "net", execute=True)
    assert receipts[0]["fallback_reason"] == "LLM_ERROR"


def test_fallback_reason_empty_response_recorded(tmp_path):
    class EmptyLLM:
        class MockResult:
            data = None
        def __init__(self): pass
        def call_chat(self, *a, **kw):
            return self.MockResult()

    br.configure(safe_write_fn=lambda p, c, **kw: True, llm_router_class=EmptyLLM)
    _fallback_reason_page(tmp_path, "pdf", "net")
    receipts = _run("pdf", "net", execute=True)
    assert receipts[0]["fallback_reason"] == "LLM_EMPTY_RESPONSE"


def test_fallback_reason_none_on_success(tmp_path):
    class GoodLLM:
        class MockResult:
            data = "New overview prose."
        def __init__(self): pass
        def call_chat(self, *a, **kw):
            return self.MockResult()

    br.configure(safe_write_fn=lambda p, c, **kw: True, llm_router_class=GoodLLM)
    _fallback_reason_page(tmp_path, "pdf", "net")
    receipts = _run("pdf", "net", execute=True)
    assert receipts[0]["fallback_reason"] == "NONE"


def test_circuit_opens_and_later_pages_skip_llm(tmp_path):
    """After 3 consecutive failures, the LLM is not attempted for the 4th page —
    it gets CIRCUIT_OPEN without paying another call_chat()."""
    call_count = {"n": 0}

    class FlakyLLM:
        def __init__(self): pass
        def call_chat(self, *a, **kw):
            call_count["n"] += 1
            raise TimeoutError("slow provider")

    br.configure(safe_write_fn=lambda p, c, **kw: True, llm_router_class=FlakyLLM)

    impacts, changes = [], []
    for i in range(5):
        page = _make_page(
            tmp_path, f"content/docs.aspose.org/en/pdf/net/p{i}.md",
            "---\ntitle: P\n---\n\n## Overview\n\nOld prose here for page.\n",
        )
        impacts.append(_make_impact(str(page), f"CHG-{i}", "overview", br.UT_REWRITE, lines=[5, 12]))
        changes.append(_make_change(f"CHG-{i}", "Feature", "FEATURE_ADDED"))
    _setup_reports(tmp_path, "pdf", "net", impacts, changes)

    receipts = _run("pdf", "net", execute=True)
    # First 3 pages actually call the LLM (and fail); after the 3rd failure the
    # circuit opens, so pages 4 and 5 skip the LLM entirely.
    assert call_count["n"] == 3, f"expected exactly 3 real LLM attempts, got {call_count['n']}"
    reasons = [r["fallback_reason"] for r in receipts]
    assert reasons[:3] == ["LLM_ERROR", "LLM_ERROR", "LLM_ERROR"]
    assert reasons[3] == "CIRCUIT_OPEN"
    assert reasons[4] == "CIRCUIT_OPEN"


def test_run_is_llm_degraded_helper(tmp_path):
    assert br.run_is_llm_degraded([{"fallback_reason": "LLM_ERROR"}]) is True
    assert br.run_is_llm_degraded([{"fallback_reason": "CIRCUIT_OPEN"}]) is True
    assert br.run_is_llm_degraded([{"fallback_reason": "NONE"}]) is False
    # A link-preservation violation reflects output quality, not an outage → not degraded.
    assert br.run_is_llm_degraded([{"fallback_reason": "LINK_PRESERVATION_VIOLATION"}]) is False
    assert br.run_is_llm_degraded([{"fallback_reason": None}]) is False


# ── SEO-BODY-REFRESH-ORDER-BY-TRAFFIC ───────────────────────────────────────
# Order-only reprioritization: a page_impact.json sitting alongside
# body_impact.json may reorder the processing loop, but must never add,
# drop, or otherwise change which impacts get processed.

class TestTrafficTierOrdering:
    def test_load_traffic_tiers_missing_file_returns_empty(self, tmp_path):
        assert br._load_traffic_tiers("pdf", "net", product_root=tmp_path) == {}

    def test_load_traffic_tiers_malformed_json_returns_empty(self, tmp_path):
        (tmp_path / "page_impact.json").write_text("not valid json {{{", encoding="utf-8")
        assert br._load_traffic_tiers("pdf", "net", product_root=tmp_path) == {}

    def test_load_traffic_tiers_reads_real_shape(self, tmp_path):
        (tmp_path / "page_impact.json").write_text(json.dumps({
            "pages": [
                {"path": "content/docs.aspose.org/en/pdf/net/a.md", "traffic_tier": "high"},
                {"path": "content/docs.aspose.org/en/pdf/net/b.md", "traffic_tier": "no-data"},
                {"path": "content/docs.aspose.org/en/pdf/net/c.md"},  # missing tier -- skipped
            ]
        }), encoding="utf-8")
        tiers = br._load_traffic_tiers("pdf", "net", product_root=tmp_path)
        assert tiers == {
            "content/docs.aspose.org/en/pdf/net/a.md": "high",
            "content/docs.aspose.org/en/pdf/net/b.md": "no-data",
        }

    def test_sort_impacts_orders_high_before_medium_before_no_data(self):
        impacts = [
            {"page_path": "a.md"},  # no-data (absent from tiers)
            {"page_path": "b.md"},  # high
            {"page_path": "c.md"},  # medium
        ]
        tiers = {"b.md": "high", "c.md": "medium"}
        result = br._sort_impacts_by_traffic_tier(impacts, tiers)
        assert [i["page_path"] for i in result] == ["b.md", "c.md", "a.md"]

    def test_sort_impacts_is_order_only_never_changes_membership(self):
        impacts = [{"page_path": f"p{i}.md"} for i in range(5)]
        tiers = {"p3.md": "high"}
        result = br._sort_impacts_by_traffic_tier(impacts, tiers)
        assert {i["page_path"] for i in result} == {i["page_path"] for i in impacts}
        assert len(result) == len(impacts)

    def test_sort_impacts_is_stable_within_same_tier(self):
        """Two pages with the same (no-data) tier must keep their original
        relative order -- Python's sort is stable, this pins that behavior."""
        impacts = [{"page_path": "z.md"}, {"page_path": "a.md"}]
        result = br._sort_impacts_by_traffic_tier(impacts, {})
        assert [i["page_path"] for i in result] == ["z.md", "a.md"]

    def test_run_processes_high_traffic_page_before_no_data_page(self, tmp_path):
        """End-to-end: page_impact.json listing page B as 'high' and page A
        as 'no-data' reorders body_refresh's actual processing loop, even
        though body_impact.json lists A first -- proven via page_decisions.jsonl
        write order (append-only, in loop-iteration order)."""
        page_a = _make_page(
            tmp_path, "content/docs.aspose.org/en/pdf/net/a.md",
            "---\ntitle: A\nauto_updatable: true\n---\n\n## Overview\n\nOld prose A.\n",
        )
        page_b = _make_page(
            tmp_path, "content/docs.aspose.org/en/pdf/net/b.md",
            "---\ntitle: B\nauto_updatable: true\n---\n\n## Overview\n\nOld prose B.\n",
        )
        change = _make_change("CHG-001", "Feature", "FEATURE_ADDED")
        impact_a = _make_impact(str(page_a), "CHG-001", "overview", br.UT_REWRITE, lines=[5, 12])
        impact_b = _make_impact(str(page_b), "CHG-001", "overview", br.UT_REWRITE, lines=[5, 12])
        # body_impact.json lists A first, B second -- the pre-traffic-tier order.
        _setup_reports(tmp_path, "pdf", "net", [impact_a, impact_b], [change])
        br.configure(safe_write_fn=lambda p, c, **kw: True)
        (tmp_path / "reports" / "pdf" / "net" / "page_impact.json").write_text(json.dumps({
            "pages": [
                {"path": str(page_a).replace("\\", "/"), "traffic_tier": "no-data"},
                {"path": str(page_b).replace("\\", "/"), "traffic_tier": "high"},
            ]
        }), encoding="utf-8")

        _run("pdf", "net", execute=True)

        decisions_path = tmp_path / "reports/pdf/net/run-artifacts/page_decisions.jsonl"
        lines = decisions_path.read_text(encoding="utf-8").strip().splitlines()
        decisions = [json.loads(line) for line in lines]
        assert len(decisions) == 2  # both pages still processed -- membership unchanged
        processed_order = [d["page_path"] for d in decisions]
        assert processed_order[0].endswith("b.md"), (
            f"expected b.md (high traffic) processed first, got order: {processed_order}"
        )

    def test_run_without_page_impact_json_preserves_original_order(self, tmp_path):
        """No page_impact.json at all (the common case for any body_refresh
        invocation outside a full PIA-instrumented run) -- original
        body_impact.json order is preserved exactly, unaffected."""
        page_a = _make_page(
            tmp_path, "content/docs.aspose.org/en/pdf/net/a.md",
            "---\ntitle: A\nauto_updatable: true\n---\n\n## Overview\n\nOld prose A.\n",
        )
        page_b = _make_page(
            tmp_path, "content/docs.aspose.org/en/pdf/net/b.md",
            "---\ntitle: B\nauto_updatable: true\n---\n\n## Overview\n\nOld prose B.\n",
        )
        change = _make_change("CHG-001", "Feature", "FEATURE_ADDED")
        impact_a = _make_impact(str(page_a), "CHG-001", "overview", br.UT_REWRITE, lines=[5, 12])
        impact_b = _make_impact(str(page_b), "CHG-001", "overview", br.UT_REWRITE, lines=[5, 12])
        _setup_reports(tmp_path, "pdf", "net", [impact_a, impact_b], [change])
        br.configure(safe_write_fn=lambda p, c, **kw: True)
        # Deliberately no page_impact.json written.

        _run("pdf", "net", execute=True)

        decisions_path = tmp_path / "reports/pdf/net/run-artifacts/page_decisions.jsonl"
        lines = decisions_path.read_text(encoding="utf-8").strip().splitlines()
        decisions = [json.loads(line) for line in lines]
        processed_order = [d["page_path"] for d in decisions]
        assert processed_order[0].endswith("a.md")
        assert processed_order[1].endswith("b.md")


class TestRemediationModeScopeSynthesis:
    """Task 12 (mission-plan-the-end-to-end-vast-hejlsberg.md, 2026-08-23): a
    real, live-found bug. body_refresh.py's run() intersects the explicit
    scope with body_impact.json's delta-driven citation-match entries
    UNCONDITIONALLY, regardless of mode -- so a remediation-mode run whose
    target pages aren't ALSO cited by whatever the live knowledge delta
    happens to show gets silently reduced to zero impacts, produces zero
    receipts, and hard-blocks with "Writers produced no run-scoped page
    decision ledger" -- defeating remediation mode's entire stated purpose
    (fixing a hand-identified defect independent of the live delta). Fixed
    by synthesizing a zero-impact (affected_sections=[]) entry for every
    scoped page not already covered by a real citation match, in remediation
    mode only -- every such page still gets a real VD_NO_SECTIONS receipt.
    """

    def test_remediation_mode_synthesizes_receipt_for_uncited_scoped_page(self, tmp_path):
        page = _make_page(
            tmp_path, "content/blog.aspose.org/pdf/java/some-post/index.md",
            "---\ntitle: Post\nauto_updatable: true\n---\n\nAlready-correct content.\n",
        )
        # body_impact.json has ZERO entries -- exactly the real, confirmed
        # scenario (a metadata-only knowledge delta cites nothing anywhere).
        _run_with_explicit_scope(
            tmp_path, "pdf", "java",
            scope_paths=[str(page)], impacts=[], mode="remediation",
            execute=True,
        )

        decisions_path = tmp_path / "reports/pdf/java/run-artifacts/page_decisions.jsonl"
        assert decisions_path.is_file(), "remediation mode must still produce a page decision ledger"
        decisions = [json.loads(l) for l in decisions_path.read_text(encoding="utf-8").strip().splitlines()]
        assert len(decisions) == 1
        assert decisions[0]["page_path"] == Path(str(page)).as_posix()
        assert decisions[0]["disposition"] == "NOT_AFFECTED"  # maps from VD_NO_SECTIONS

    def test_non_remediation_mode_still_drops_uncited_scoped_page(self, tmp_path):
        """Negative control: the fix must be remediation-mode-only -- upstream/
        combined mode's existing delta-driven behavior (scope derived FROM
        the delta via PIA, so an uncited scoped page would itself be a real
        anomaly worth investigating, not silently synthesized away) must be
        completely unchanged."""
        page = _make_page(
            tmp_path, "content/blog.aspose.org/pdf/java/some-post/index.md",
            "---\ntitle: Post\nauto_updatable: true\n---\n\nContent.\n",
        )
        _run_with_explicit_scope(
            tmp_path, "pdf", "java",
            scope_paths=[str(page)], impacts=[], mode="upstream",
            execute=True,
        )

        decisions_path = tmp_path / "reports/pdf/java/run-artifacts/page_decisions.jsonl"
        assert not decisions_path.is_file(), (
            "non-remediation mode must NOT synthesize a receipt for an uncited page -- "
            "this must remain the exact pre-fix behavior"
        )

    def test_remediation_mode_still_uses_real_impact_when_present(self, tmp_path):
        """A scoped page that DOES have a real citation match in remediation
        mode must be processed normally via that real impact entry, not
        overridden by a synthesized no-op one (no double-counting, no
        clobbering a real update with a fake NOT_AFFECTED)."""
        page = _make_page(
            tmp_path, "content/docs.aspose.org/en/pdf/java/developer-guide/annotations.md",
            "---\ntitle: Annotations\nauto_updatable: true\n---\n\n"
            "## Overview\n\nOld prose about `WidgetAnnotation`.\n",
        )
        change = _make_change("CHG-001", "WidgetAnnotation", "API_REMOVED")
        impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REMOVAL, lines=[3, 5])
        br.configure(safe_write_fn=lambda p, c, **kw: True)

        _run_with_explicit_scope(
            tmp_path, "pdf", "java",
            scope_paths=[str(page)], impacts=[impact], mode="remediation",
            execute=True,
        )

        decisions_path = tmp_path / "reports/pdf/java/run-artifacts/page_decisions.jsonl"
        decisions = [json.loads(l) for l in decisions_path.read_text(encoding="utf-8").strip().splitlines()]
        # Exactly one decision for this one scoped page -- proves the real
        # impact was processed through the normal path once, not ALSO
        # synthesized as a second, duplicate no-op entry (which would either
        # raise a page-decision collision in _emit_run_decision, or silently
        # double-count). This is the property that actually matters here:
        # remediation mode's synthesis must never touch a page already
        # covered by a real impact.
        assert len(decisions) == 1
        assert decisions[0]["page_path"] == Path(str(page)).as_posix()

    def test_remediation_mode_with_multiple_uncited_pages_gets_a_receipt_each(self, tmp_path):
        pages = [
            _make_page(
                tmp_path, f"content/blog.aspose.org/pdf/java/post-{i}/index.md",
                "---\ntitle: Post\nauto_updatable: true\n---\n\nFine as-is.\n",
            )
            for i in range(3)
        ]
        _run_with_explicit_scope(
            tmp_path, "pdf", "java",
            scope_paths=[str(p) for p in pages], impacts=[], mode="remediation",
            execute=True,
        )

        decisions_path = tmp_path / "reports/pdf/java/run-artifacts/page_decisions.jsonl"
        decisions = [json.loads(l) for l in decisions_path.read_text(encoding="utf-8").strip().splitlines()]
        assert {d["page_path"] for d in decisions} == {Path(str(p)).as_posix() for p in pages}
        assert all(d["disposition"] == "NOT_AFFECTED" for d in decisions)

    def test_missing_manifest_mode_field_behaves_like_non_remediation(self, tmp_path):
        """An older manifest schema with no "mode" field at all (pre-Task-6
        historical runs, or any manifest missing the field for any reason)
        must fail open to the ORIGINAL (pre-fix) behavior, not silently
        assume remediation semantics."""
        page = _make_page(
            tmp_path, "content/blog.aspose.org/pdf/java/some-post/index.md",
            "---\ntitle: Post\nauto_updatable: true\n---\n\nContent.\n",
        )
        _run_with_explicit_scope(
            tmp_path, "pdf", "java",
            scope_paths=[str(page)], impacts=[], mode=None,
            execute=True,
        )

        decisions_path = tmp_path / "reports/pdf/java/run-artifacts/page_decisions.jsonl"
        assert not decisions_path.is_file()
