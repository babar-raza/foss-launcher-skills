"""Focused tests for the run-bound S-84 refresh control plane."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import refresh_run
from commands.content.body_refresh import _frontmatter_hash, _normalized_body_hash
from lib.reference_filter import GROUPED_INDEX_GENERATOR_VERSION


MODEL_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _write_empty_backlink_manifest(args: list[str]) -> None:
    """TC12 (2026-08-21): apply_run()'s new backlink-reconciliation step
    always invokes backlink_backfill.py --output <path> and requires that
    file to exist with a valid total_errors/changes shape. Every stub
    command_runner in this file that doesn't specifically test backlink
    reconciliation must still satisfy this contract, so it's centralized
    here rather than duplicated across every fixture."""
    str_args = [str(a) for a in args]
    if "backlink_backfill.py" not in " ".join(str_args):
        return
    if "--output" not in str_args:
        return
    out_path = Path(str_args[str_args.index("--output") + 1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "generated_at": "2026-07-25T00:00:00+00:00",
        "generator": "test-stub",
        "dry_run": False,
        "total_candidates": 0,
        "total_modified": 0,
        "total_skipped": 0,
        "total_errors": 0,
        "changes": [],
        "errors": [],
        "rollback_commands": [],
    }), encoding="utf-8")


def _runner(
    args: list[str],
    **_: object,
) -> subprocess.CompletedProcess[str]:
    if args[:3] == ["git", "rev-parse", "HEAD"]:
        return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
    _write_empty_backlink_manifest(args)
    return subprocess.CompletedProcess(args, 0, "", "")


def _write_run_evidence(
    tmp_path: Path,
    manifest: dict,
    *,
    validator_value: str = "PASS",
    dispositions: dict[str, str] | None = None,
    include_validation: bool = False,
) -> list[dict]:
    """Create a complete, internally consistent synthetic run evidence bundle."""
    run_root = (
        tmp_path
        / "reports/refresh_runs"
        / manifest["family"]
        / manifest["platform"]
        / manifest["run_id"]
    )
    scope_paths = list(manifest["scope"]["paths"])
    initial_hashes: dict[str, str] = {}
    decisions: list[dict] = []
    receipts: list[Path] = []
    for index, relative in enumerate(scope_paths, 1):
        page = tmp_path / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        if not page.is_file():
            page.write_text(
                "---\ntitle: Test\n---\n\nGrounded body.\n",
                encoding="utf-8",
            )
        content = page.read_text(encoding="utf-8")
        file_hash = refresh_run._path_hash(relative)
        initial_hashes[relative] = file_hash
        receipt_path = run_root / "receipts" / f"RCP-{index:03d}.yaml"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            yaml.safe_dump(
                {
                    "content_refresh_receipt": {
                        "receipt_id": f"RCP-{index:03d}",
                        "run_id": manifest["run_id"],
                        "page_path": relative,
                        "old_hash": file_hash,
                        "new_hash": file_hash,
                    }
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        receipts.append(receipt_path)
        decisions.append(
            {
                "schema_version": 1,
                "run_id": manifest["run_id"],
                "page_path": relative,
                "surface": "docs",
                "locale": "en",
                "intended_action": "BODY_UPDATE",
                "disposition": (
                    dispositions or {}
                ).get(relative, "BODY_UPDATED"),
                "body_hash_before": (
                    "sha256:" + "0" * 64
                    if (dispositions or {}).get(relative, "BODY_UPDATED")
                    == "BODY_UPDATED"
                    else _normalized_body_hash(content)
                ),
                "body_hash_after": _normalized_body_hash(content),
                "frontmatter_hash_before": _frontmatter_hash(content),
                "frontmatter_hash_after": _frontmatter_hash(content),
                "receipt_ref": receipt_path.relative_to(run_root).as_posix(),
                "receipt_digest": refresh_run._file_digest(receipt_path),
                "evidence_claims_checked": [],
                "evidence_apis_checked": [],
                "validator_results": {
                    "receipt": "PASS",
                    "forbidden_claims": validator_value,
                    "regrounding": validator_value,
                },
            }
        )
    scope_path = run_root / "scope.json"
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": manifest["run_id"],
                "family": manifest["family"],
                "platform": manifest["platform"],
                "paths": scope_paths,
                "initial_hashes": initial_hashes,
            }
        ),
        encoding="utf-8",
    )
    manifest["scope"]["digest"] = refresh_run._scope_digest(
        scope_paths, manifest["scope"].get("input_digest")
    )
    decisions_path = run_root / "page_decisions.jsonl"
    decisions_path.write_text(
        "".join(json.dumps(row) + "\n" for row in decisions),
        encoding="utf-8",
    )
    manifest["receipt_refs"] = [
        path.relative_to(tmp_path).as_posix() for path in receipts
    ]
    manifest["page_decision_ref"] = decisions_path.relative_to(tmp_path).as_posix()
    manifest["output_digests"]["scope"] = refresh_run._file_digest(scope_path)
    manifest["output_digests"]["page_decisions"] = refresh_run._file_digest(
        decisions_path
    )
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        "\n".join(
            f"{path.name}:{refresh_run._file_digest(path)}" for path in receipts
        ).encode("utf-8")
    ).hexdigest()
    if include_validation:
        details = {}
        validation_attempt_root = run_root / "validation/attempt-01"
        validation_attempt_root.mkdir(parents=True, exist_ok=True)
        for field in refresh_run.VALIDATION_FIELDS:
            stdout_path = validation_attempt_root / f"{field}.stdout.log"
            stderr_path = validation_attempt_root / f"{field}.stderr.log"
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            details[field] = {
                "stdout_ref": stdout_path.relative_to(run_root).as_posix(),
                "stderr_ref": stderr_path.relative_to(run_root).as_posix(),
                "stdout_digest": refresh_run._file_digest(stdout_path),
                "stderr_digest": refresh_run._file_digest(stderr_path),
            }
        validation_payload = {
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "results": manifest["validation"],
            "details": details,
        }
        attempt_path = validation_attempt_root / "result.json"
        attempt_path.write_text(
            json.dumps(validation_payload), encoding="utf-8"
        )
        validation_path = run_root / "validation.json"
        validation_path.write_text(
            json.dumps(validation_payload),
            encoding="utf-8",
        )
        manifest["validation_attempt_refs"] = [
            attempt_path.relative_to(run_root).as_posix()
        ]
        manifest["validation_attempt_digests"] = {
            manifest["validation_attempt_refs"][0]:
            refresh_run._file_digest(attempt_path)
        }
        manifest["output_digests"]["validation"] = refresh_run._file_digest(
            validation_path
        )
    refresh_run._save_manifest(manifest)
    return decisions


def _replace_synthetic_output(
    tmp_path: Path,
    manifest: dict,
    *,
    page_path: str,
    content: str,
) -> None:
    """Update a synthetic bundle as if its writer atomically produced *content*."""
    run_root = (
        tmp_path
        / "reports/refresh_runs"
        / manifest["family"]
        / manifest["platform"]
        / manifest["run_id"]
    )
    page = tmp_path / page_path
    page.write_text(content, encoding="utf-8")
    output_hash = refresh_run._path_hash(page_path)
    decisions_path = run_root / "page_decisions.jsonl"
    rows = [
        json.loads(line)
        for line in decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if row["page_path"] != page_path:
            continue
        receipt_path = run_root / row["receipt_ref"]
        receipt_doc = yaml.safe_load(receipt_path.read_text(encoding="utf-8"))
        receipt_doc["content_refresh_receipt"]["new_hash"] = output_hash
        receipt_path.write_text(
            yaml.safe_dump(receipt_doc, sort_keys=False),
            encoding="utf-8",
        )
        row["body_hash_after"] = _normalized_body_hash(content)
        row["frontmatter_hash_after"] = _frontmatter_hash(content)
        row["receipt_digest"] = refresh_run._file_digest(receipt_path)
    decisions_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    receipts = sorted((run_root / "receipts").glob("*.yaml"))
    manifest["output_digests"]["page_decisions"] = refresh_run._file_digest(
        decisions_path
    )
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        "\n".join(
            f"{path.name}:{refresh_run._file_digest(path)}" for path in receipts
        ).encode("utf-8")
    ).hexdigest()
    refresh_run._save_manifest(manifest)


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model_path = tmp_path / "knowledge/pdf/net/merged/model.yaml"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        yaml.safe_dump(
            {
                "family": "pdf",
                "platform": "net",
                "repo_sha": MODEL_SHA,
                "stale_since": None,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    # CLAUDE_CODE_SESSION_ID is set by the real harness running this very test
    # suite (production concurrency redesign, 2026-08-01, Step 2 added it as a
    # third _session_id fallback tier) -- must be cleared here too or
    # test_start_requires_stable_session_identity below silently passes for
    # the wrong reason only when run inside an actual Claude Code session.
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    yield
    refresh_run.configure()


def test_start_creates_valid_input_pinned_manifest(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-001",
        session_id="session-1",
    )
    assert manifest["state"] == "INPUTS_PINNED"
    assert manifest["base_commit_sha"] == HEAD_SHA
    assert manifest["initial_model_sha"] == MODEL_SHA
    assert manifest["initial_source_sha"] == MODEL_SHA
    assert manifest["session_owner"] == "session-1"

    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-001"
    assert (run_root / "manifest.json").is_file()
    assert (run_root / "events.jsonl").is_file()
    active = json.loads(
        (tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json").read_text(
            encoding="utf-8"
        )
    )
    assert active["run_id"] == "RUN-001"


def test_start_requires_stable_session_identity():
    with pytest.raises(refresh_run.RefreshRunError, match="stable session identity"):
        refresh_run.create_run("pdf", "net", mode="upstream")


def test_codex_thread_identity_is_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread-1")
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-CODEX"
    )
    assert manifest["session_owner"] == "codex-thread-1"


def test_claude_code_session_id_identity_is_accepted(monkeypatch: pytest.MonkeyPatch):
    """Step 2 of the production concurrency redesign (2026-08-01): previously
    the weakest of 4 duplicate identity-resolution copies -- this was the
    only one that hard-errored instead of falling back to the harness's own
    per-conversation id. Now routed through lib/session_identity.py, matching
    skill_context.py's precedence exactly."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "conv-uuid-1")
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-CLAUDE"
    )
    assert manifest["session_owner"] == "conv-uuid-1"


def test_agent_session_id_takes_precedence_over_claude_code_session_id(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AGENT_SESSION_ID", "agent-sess")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "conv-uuid-1")
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-PRECEDENCE"
    )
    assert manifest["session_owner"] == "agent-sess"


def test_remediation_requires_scope_manifest():
    with pytest.raises(refresh_run.RefreshRunError, match="requires --scope-manifest"):
        refresh_run.create_run(
            "pdf",
            "net",
            mode="remediation",
            run_id="RUN-REMEDIATION",
            session_id="session-1",
        )


def test_remediation_rejects_model_clone_mismatch(tmp_path: Path):
    scope = tmp_path / "scope.json"
    scope.write_text('{"paths":[]}', encoding="utf-8")
    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=_runner,
        source_sha_resolver=lambda _f, _p: "c" * 40,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    with pytest.raises(refresh_run.RefreshRunError, match="requires current knowledge"):
        refresh_run.create_run(
            "pdf",
            "net",
            mode="remediation",
            scope_manifest="scope.json",
            run_id="RUN-MISMATCH",
            session_id="session-1",
        )
    assert not (
        tmp_path / "reports/refresh_runs/pdf/net/RUN-MISMATCH"
    ).exists(), "failed preflight must not leave an orphan run directory"


def test_scope_manifest_rejects_path_traversal(tmp_path: Path):
    scope = tmp_path / "scope.json"
    scope.write_text('{"paths":["../outside.md"]}', encoding="utf-8")
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="remediation",
        scope_manifest="scope.json",
        run_id="RUN-SCOPE",
        session_id="session-1",
    )
    with pytest.raises(refresh_run.RefreshRunError, match="Unsafe scope path"):
        refresh_run.prepare_run(manifest)


def test_scope_manifest_digest_is_rechecked_before_planning(tmp_path: Path):
    selected = "content/docs.aspose.org/en/pdf/net/selected.md"
    page = tmp_path / selected
    page.parent.mkdir(parents=True)
    page.write_text("page\n", encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"paths": [selected]}), encoding="utf-8")
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="remediation",
        scope_manifest="scope.json",
        run_id="RUN-SCOPE-DIGEST",
        session_id="session-1",
    )
    scope.write_text(json.dumps({"paths": []}), encoding="utf-8")

    with pytest.raises(refresh_run.RefreshRunError, match="changed after INPUTS_PINNED"):
        refresh_run.prepare_run(manifest)


def test_assert_product_scope_accepts_real_per_site_path_shapes():
    """Regression test for a confirmed bug: this function special-cased
    "products.aspose.org" as the site with NO locale segment -- backwards.
    Real path shapes (verified live against the repo, MT014-2026-07-29-
    PDF-GO-REDO): every site except blog.aspose.org carries an English
    locale segment, INCLUDING products.aspose.org (its other top-level
    entries are non-English locale codes like ar/bg/ca, confirming "en" is
    a real locale directory there, not absent) -- only blog.aspose.org
    omits it (its non-English variants suffix the filename instead, e.g.
    index.fr.md). The old code rejected every real blog/products path in
    scope as "outside the product"."""
    real_paths = [
        "content/docs.aspose.org/en/pdf/go/_index.md",
        "content/kb.aspose.org/en/pdf/go/faq.md",
        "content/reference.aspose.org/en/pdf/go/Document.md",
        "content/products.aspose.org/en/pdf/go/_index.md",
        "content/blog.aspose.org/pdf/go/_index.md",
        "content/blog.aspose.org/pdf/go/pdf-document-management-go/index.md",
    ]
    refresh_run._assert_product_scope(real_paths, "pdf", "go")  # must not raise


def test_assert_product_scope_rejects_blog_path_with_locale_segment():
    """Negative control: blog.aspose.org must NOT accept a spurious 'en'
    segment either -- it genuinely has none in real content."""
    with pytest.raises(refresh_run.RefreshRunError, match="outside pdf/go"):
        refresh_run._assert_product_scope(
            ["content/blog.aspose.org/en/pdf/go/_index.md"], "pdf", "go"
        )


def test_assert_product_scope_rejects_products_path_without_locale():
    """Negative control: products.aspose.org must NOT accept a path missing
    its real locale segment."""
    with pytest.raises(refresh_run.RefreshRunError, match="outside pdf/go"):
        refresh_run._assert_product_scope(
            ["content/products.aspose.org/pdf/go/_index.md"], "pdf", "go"
        )


def test_assert_product_scope_rejects_cross_product_path():
    with pytest.raises(refresh_run.RefreshRunError, match="outside pdf/go"):
        refresh_run._assert_product_scope(
            ["content/docs.aspose.org/en/words/net/other.md"], "pdf", "go"
        )


def test_prepare_rejects_scope_from_another_product(tmp_path: Path):
    selected = "content/docs.aspose.org/en/words/net/selected.md"
    page = tmp_path / selected
    page.parent.mkdir(parents=True)
    page.write_text("page\n", encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"paths": [selected]}), encoding="utf-8")
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="remediation",
        scope_manifest="scope.json",
        run_id="RUN-WRONG-PRODUCT",
        session_id="session-1",
    )

    with pytest.raises(refresh_run.RefreshRunError, match="outside pdf/net"):
        refresh_run.prepare_run(manifest)


def test_prepare_rejects_dirty_scoped_base(tmp_path: Path):
    selected = "content/docs.aspose.org/en/pdf/net/selected.md"
    page = tmp_path / selected
    page.parent.mkdir(parents=True)
    page.write_text("pre-existing edit\n", encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"paths": [selected]}), encoding="utf-8")

    def dirty_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:3] == ["git", "diff", "--quiet"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=dirty_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="remediation",
        scope_manifest="scope.json",
        run_id="RUN-DIRTY-BASE",
        session_id="session-1",
    )

    with pytest.raises(refresh_run.RefreshRunError, match="clean scoped base"):
        refresh_run.prepare_run(manifest)


def test_combined_mode_does_not_block_on_its_own_knowledge_refresh_evidence(
    tmp_path: Path,
):
    """Regression test for a confirmed bug: the "clean scoped base" check
    compared scoped pages directly against base_commit_sha, but knowledge
    refresh's own attach_evidence.py sub-step (run earlier in this SAME
    prepare_run call, for upstream/combined mode) legitimately rewrites
    those exact pages' evidence.model_sha before scope is even computed --
    so every real combined/upstream run blocked on its own legitimate
    output, unconditionally. Found live during MT014-2026-07-29-PDF-GO-REDO
    (the one prior combined-mode attempt on record, cells/go's
    mt011-cells-go-ref, never got far enough to hit this specific check,
    but would have). Fix: snapshot which pages are dirty immediately after
    knowledge refresh finishes; only block if a scoped page differs from
    THAT snapshot (something touched it again afterward), not from
    base_commit_sha directly."""
    evidence_touched = "content/docs.aspose.org/en/pdf/net/touched.md"
    untouched = "content/docs.aspose.org/en/pdf/net/untouched.md"
    for relative in (evidence_touched, untouched):
        page = tmp_path / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("page\n", encoding="utf-8")

    delta_path = tmp_path / "knowledge/pdf/net/merged/knowledge_delta.json"
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text("{}", encoding="utf-8")

    def kr_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:4] == ["git", "diff", "--name-only", HEAD_SHA]:
            # Simulates: knowledge refresh's attach_evidence.py already
            # rewrote `evidence_touched` by the time this snapshot runs.
            return subprocess.CompletedProcess(
                args, 0, f"{evidence_touched}\n", ""
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=kr_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-KR-EVIDENCE",
        session_id="session-1",
    )
    planning = (
        tmp_path / "reports/refresh_runs/pdf/net/RUN-KR-EVIDENCE/planning/pdf/net"
    )
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"path": evidence_touched, "pia_score": "HIGH_IMPACT"},
                    {"path": untouched, "pia_score": "HIGH_IMPACT"},
                ]
            }
        ),
        encoding="utf-8",
    )

    prepared = refresh_run.prepare_run(manifest)  # must not raise

    assert prepared["scope"]["paths"] == sorted([evidence_touched, untouched])


def test_combined_mode_still_blocks_on_a_change_after_knowledge_refresh(
    tmp_path: Path,
):
    """Negative control: the fix above must not become a blanket bypass --
    a page that changes AGAIN after knowledge refresh's own snapshot (a
    genuinely concurrent/unexpected edit) must still block."""
    tampered = "content/docs.aspose.org/en/pdf/net/tampered.md"
    page = tmp_path / tampered
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("original\n", encoding="utf-8")

    delta_path = tmp_path / "knowledge/pdf/net/merged/knowledge_delta.json"
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text("{}", encoding="utf-8")

    def kr_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:4] == ["git", "diff", "--name-only", HEAD_SHA]:
            # Snapshot point: file still has its "original" content here.
            return subprocess.CompletedProcess(args, 0, f"{tampered}\n", "")
        if any("site_planner.py" in str(a) for a in args):
            # Simulate a concurrent edit landing well after the post-KR
            # snapshot was taken but before the later dirty-check runs.
            page.write_text("tampered after knowledge refresh\n", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=kr_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-KR-TAMPERED",
        session_id="session-1",
    )
    planning = (
        tmp_path / "reports/refresh_runs/pdf/net/RUN-KR-TAMPERED/planning/pdf/net"
    )
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps({"pages": [{"path": tampered, "pia_score": "HIGH_IMPACT"}]}),
        encoding="utf-8",
    )

    with pytest.raises(refresh_run.RefreshRunError, match="clean scoped base"):
        refresh_run.prepare_run(manifest)


def test_remediation_scope_is_not_broadened_by_historical_pia(tmp_path: Path):
    selected = "content/docs.aspose.org/en/pdf/net/selected.md"
    historical = "content/docs.aspose.org/en/pdf/net/historical.md"
    for relative in (selected, historical):
        page = tmp_path / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("page\n", encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(
        json.dumps({"paths": [selected]}),
        encoding="utf-8",
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="remediation",
        scope_manifest="scope.json",
        run_id="RUN-EXACT-SCOPE",
        session_id="session-1",
    )
    planning = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-EXACT-SCOPE/planning/pdf/net"
    )
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"path": selected, "pia_score": "HIGH_IMPACT"},
                    {"path": historical, "pia_score": "HIGH_IMPACT"},
                ]
            }
        ),
        encoding="utf-8",
    )

    prepared = refresh_run.prepare_run(manifest)

    assert prepared["scope"]["paths"] == [selected]
    saved_scope = json.loads(
        (
            tmp_path
            / "reports/refresh_runs/pdf/net/RUN-EXACT-SCOPE/scope.json"
        ).read_text(encoding="utf-8")
    )
    assert saved_scope["paths"] == [selected]


def _remediation_manifest_with_scope(tmp_path: Path, run_id: str, family="pdf", platform="net"):
    """Shared minimal remediation-mode setup that lets prepare_run() complete
    successfully -- mirrors test_scope_manifest_digest_is_rechecked_before_planning's
    sibling above, factored out for the fact-pack tests below (Task 4, S9.2)."""
    selected = f"content/docs.aspose.org/en/{family}/{platform}/selected.md"
    page = tmp_path / selected
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("page\n", encoding="utf-8")
    scope = tmp_path / f"scope-{run_id}.json"
    scope.write_text(json.dumps({"paths": [selected]}), encoding="utf-8")
    manifest = refresh_run.create_run(
        family, platform, mode="remediation",
        scope_manifest=f"scope-{run_id}.json", run_id=run_id, session_id="session-1",
    )
    planning = tmp_path / f"reports/refresh_runs/{family}/{platform}/{run_id}/planning/{family}/{platform}"
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps({"pages": [{"path": selected, "pia_score": "HIGH_IMPACT"}]}),
        encoding="utf-8",
    )
    return manifest


def _write_fact_pack(tmp_path: Path, mission_id: str, *, family="pdf", platform="net",
                      version="26.8.0", group_id="org.aspose", artifact_id="aspose-pdf-foss"):
    handoff_dir = tmp_path / "reports" / "handoff" / mission_id
    handoff_dir.mkdir(parents=True, exist_ok=True)
    fact_pack_path = handoff_dir / "fact-pack.json"
    fact_pack_path.write_text(json.dumps({
        "product": {"family": family, "platform": platform},
        "version": {"previous": "26.6.0", "new": version},
        "maven": {"group_id": group_id, "artifact_id": artifact_id},
    }), encoding="utf-8")
    return fact_pack_path


def _write_registry_candidate(tmp_path: Path, *, family="pdf", platform="net",
                               version="26.8.0", group_id="org.aspose", artifact_id="aspose-pdf-foss"):
    registry_path = tmp_path / "data" / "package_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({
        family: {platform: {"candidate": {
            "group_id": group_id, "artifact_id": artifact_id, "version": version,
        }}}
    }), encoding="utf-8")


def test_prepare_run_reads_matching_fact_pack_with_no_mismatch(tmp_path: Path):
    """Task 4 (S9.2): a fact pack that agrees with package_registry.json's
    candidate must be picked up (fact_pack_ref set) and must never block."""
    _write_fact_pack(tmp_path, "MT-TEST-2026-08-23-PDF-NET")
    _write_registry_candidate(tmp_path)
    manifest = _remediation_manifest_with_scope(tmp_path, "RUN-FACTPACK-OK")

    prepared = refresh_run.prepare_run(manifest)

    assert prepared["fact_pack_ref"] == "reports/handoff/MT-TEST-2026-08-23-PDF-NET/fact-pack.json"


def test_prepare_run_proceeds_with_no_fact_pack_ref_when_none_found(tmp_path: Path):
    """Documented fallback (S9.2): no fact pack for this product yet must
    never block -- fact_pack_ref is simply None."""
    manifest = _remediation_manifest_with_scope(tmp_path, "RUN-NO-FACTPACK")

    prepared = refresh_run.prepare_run(manifest)

    assert prepared["fact_pack_ref"] is None


def test_prepare_run_blocks_on_fact_pack_version_mismatch(tmp_path: Path):
    """F9's mechanical fix: a fact pack's version.new disagreeing with
    package_registry.json's candidate.version must fail fast, before any of
    prepare_run's heavier downstream work runs -- exactly the class of drift
    that let pdf/java render a stale Maven version in production for real."""
    _write_fact_pack(tmp_path, "MT-TEST-2026-08-23-PDF-NET-MISMATCH", version="26.9.0")
    _write_registry_candidate(tmp_path, version="26.8.0")
    manifest = _remediation_manifest_with_scope(tmp_path, "RUN-FACTPACK-MISMATCH")

    with pytest.raises(refresh_run.RefreshRunError, match="disagrees with data/package_registry.json"):
        refresh_run.prepare_run(manifest)


def test_prepare_run_blocks_on_fact_pack_maven_coordinate_mismatch(tmp_path: Path):
    _write_fact_pack(tmp_path, "MT-TEST-2026-08-23-PDF-NET-GID", artifact_id="aspose-pdf")
    _write_registry_candidate(tmp_path, artifact_id="aspose-pdf-foss")
    manifest = _remediation_manifest_with_scope(tmp_path, "RUN-FACTPACK-GID-MISMATCH")

    with pytest.raises(refresh_run.RefreshRunError, match="maven.artifact_id"):
        refresh_run.prepare_run(manifest)


def test_discover_fact_pack_picks_most_recently_modified_when_multiple_match(tmp_path: Path):
    refresh_run.configure(repo_root=tmp_path)
    older = _write_fact_pack(tmp_path, "MT-OLD-2026-08-01-PDF-NET", version="26.7.0")
    newer = _write_fact_pack(tmp_path, "MT-NEW-2026-08-21-PDF-NET", version="26.8.0")
    import os as _os
    now = _os.path.getmtime(newer)
    _os.utime(older, (now - 100, now - 100))

    found = refresh_run._discover_fact_pack("pdf", "net")

    assert found["version"]["new"] == "26.8.0"


def test_upstream_scope_selected_from_real_pia_score_schema(tmp_path: Path):
    """Regression test for a confirmed bug: page_impact_assess.py's real,
    documented output field is "pia_score" (not "impact"/"impact_level"/
    "classification"), but _paths_from_pia() only checked the latter three --
    so every real upstream/combined-mode run with genuine HIGH_IMPACT/
    MEDIUM_IMPACT pages incorrectly resolved to zero scope and raised
    "Refresh scope resolved to zero pages" (found live during
    MT014-2026-07-29-PDF-GO-REDO's first real refresh_run.py execution
    against pdf/go, which had 55 HIGH_IMPACT + 8 MEDIUM_IMPACT real pages).
    test_remediation_scope_is_not_broadened_by_historical_pia (above) never
    caught this because remediation mode never consults PIA scope at all,
    and its own fixture used the wrong field name too."""
    high = "content/docs.aspose.org/en/pdf/net/high.md"
    medium = "content/docs.aspose.org/en/pdf/net/medium.md"
    low = "content/docs.aspose.org/en/pdf/net/low.md"
    not_affected = "content/docs.aspose.org/en/pdf/net/not-affected.md"
    for relative in (high, medium, low, not_affected):
        page = tmp_path / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("page\n", encoding="utf-8")

    delta_path = tmp_path / "knowledge/pdf/net/merged/knowledge_delta.json"
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text("{}", encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-PIA-SCORE",
        session_id="session-1",
    )
    planning = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-PIA-SCORE/planning/pdf/net"
    )
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"path": high, "pia_score": "HIGH_IMPACT"},
                    {"path": medium, "pia_score": "MEDIUM_IMPACT"},
                    {"path": low, "pia_score": "LOW_IMPACT"},
                    {"path": not_affected, "pia_score": "NOT_AFFECTED"},
                ]
            }
        ),
        encoding="utf-8",
    )

    prepared = refresh_run.prepare_run(manifest)

    assert prepared["scope"]["paths"] == sorted([high, medium])


def test_pia_scope_excludes_protected_pages(tmp_path: Path):
    """Regression test for a confirmed bug (2026-08-28, cells/net + 3d/python
    batch-6 refreshes): page_impact_assess.py's PIA scoring has no concept
    of content protection, so a page marked auto_updatable:false or
    manually curated but flagged HIGH/MEDIUM_IMPACT (its underlying API
    changed) still got pinned into scope via pia_scope_paths -- even though
    _full_reference_scope_paths() (batch_reference.py's own rebuild_all
    dry-run) already, correctly, excludes protected reference pages from
    its own contribution. apply_run()'s real write then correctly respects
    the protection and skips the page (disposition=BLOCKED), but with no
    valid decision for a page still pinned in scope, that trips the "N
    scoped page decision(s) are BLOCKED" hard block for a page nothing was
    ever going to write to -- confirmed live on cells/net (10 pages,
    e.g. Cell.md, auto_updatable:false since 2026-04) and 3d/python (1 KB
    page). Fixed via _filter_protected_paths()."""
    normal = "content/docs.aspose.org/en/pdf/net/normal.md"
    protected = "content/docs.aspose.org/en/pdf/net/protected.md"
    manually_curated = "content/docs.aspose.org/en/pdf/net/manually-curated.md"
    for relative in (normal,):
        page = tmp_path / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("page\n", encoding="utf-8")
    (tmp_path / protected).write_text(
        "---\nprovenance:\n  auto_updatable: false\n---\nprotected page\n",
        encoding="utf-8",
    )
    (tmp_path / manually_curated).write_text(
        "---\nprovenance:\n  last_mechanism: manual-edit-skill\n---\ncurated page\n",
        encoding="utf-8",
    )
    delta_path = tmp_path / "knowledge/pdf/net/merged/knowledge_delta.json"
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text("{}", encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-PIA-PROTECTED", session_id="session-1",
    )
    planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-PIA-PROTECTED/planning/pdf/net"
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"path": normal, "pia_score": "HIGH_IMPACT"},
                    {"path": protected, "pia_score": "HIGH_IMPACT"},
                    {"path": manually_curated, "pia_score": "HIGH_IMPACT"},
                ]
            }
        ),
        encoding="utf-8",
    )

    prepared = refresh_run.prepare_run(manifest)

    assert normal in prepared["scope"]["paths"]
    assert protected not in prepared["scope"]["paths"]
    assert manually_curated not in prepared["scope"]["paths"]


def test_prepare_run_sets_blog_announcement_required_true_for_real_delta(tmp_path: Path):
    """Task 6 (S9.6, corrected): a real, non-empty knowledge_delta.json must
    set manifest["blog_announcement_required"] -- the deterministic half of
    the mandatory-per-release blog announcement decision; the actual
    drafting is directed by the new blog-release-check skill (S-124), not
    performed by this code."""
    page = tmp_path / "content/docs.aspose.org/en/pdf/net/page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("page\n", encoding="utf-8")

    delta_path = tmp_path / "knowledge/pdf/net/merged/knowledge_delta.json"
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text(json.dumps({"new_apis": ["Align"]}), encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-BLOG-REAL", session_id="session-1",
    )
    planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-BLOG-REAL/planning/pdf/net"
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps({"pages": [{"path": str(page.relative_to(tmp_path).as_posix()), "pia_score": "HIGH_IMPACT"}]}),
        encoding="utf-8",
    )

    prepared = refresh_run.prepare_run(manifest)

    assert prepared["blog_announcement_required"] is True


def test_prepare_run_sets_blog_announcement_required_false_for_no_op_delta(tmp_path: Path):
    """Negative control: a no-op sync (repo_sha advanced, zero real API/claim
    change) must never force an announcement -- this is what S9.6's own
    "still gated on a real delta existing at all" scoping means."""
    page = tmp_path / "content/docs.aspose.org/en/pdf/net/page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("page\n", encoding="utf-8")

    delta_path = tmp_path / "knowledge/pdf/net/merged/knowledge_delta.json"
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text("{}", encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-BLOG-NOOP", session_id="session-1",
    )
    planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-BLOG-NOOP/planning/pdf/net"
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps({"pages": [{"path": str(page.relative_to(tmp_path).as_posix()), "pia_score": "HIGH_IMPACT"}]}),
        encoding="utf-8",
    )

    prepared = refresh_run.prepare_run(manifest)

    assert prepared["blog_announcement_required"] is False


class TestKnowledgeDeltaIsReal:
    def test_empty_dict_is_not_real(self, tmp_path: Path):
        delta_path = tmp_path / "knowledge_delta.json"
        delta_path.write_text("{}", encoding="utf-8")
        assert refresh_run._knowledge_delta_is_real(delta_path) is False

    def test_all_empty_lists_is_not_real(self, tmp_path: Path):
        delta_path = tmp_path / "knowledge_delta.json"
        delta_path.write_text(json.dumps({
            "new_claims": [], "removed_claims": [], "modified_claims": [],
            "new_apis": [], "removed_apis": [], "modified_apis": [], "resurrected_apis": [],
        }), encoding="utf-8")
        assert refresh_run._knowledge_delta_is_real(delta_path) is False

    def test_one_non_empty_list_is_real(self, tmp_path: Path):
        delta_path = tmp_path / "knowledge_delta.json"
        delta_path.write_text(json.dumps({"resurrected_apis": ["Foo"]}), encoding="utf-8")
        assert refresh_run._knowledge_delta_is_real(delta_path) is True

    def test_malformed_json_fails_open_to_false(self, tmp_path: Path):
        delta_path = tmp_path / "knowledge_delta.json"
        delta_path.write_text("not json{{{", encoding="utf-8")
        assert refresh_run._knowledge_delta_is_real(delta_path) is False

    def test_missing_file_fails_open_to_false(self, tmp_path: Path):
        assert refresh_run._knowledge_delta_is_real(tmp_path / "does-not-exist.json") is False

    def test_non_dict_json_fails_open_to_false(self, tmp_path: Path):
        delta_path = tmp_path / "knowledge_delta.json"
        delta_path.write_text("[1, 2, 3]", encoding="utf-8")
        assert refresh_run._knowledge_delta_is_real(delta_path) is False


class TestFullReferenceScopeResolution:
    """G17 deep-reassessment pass (2026-08-24): prepare_run's scope
    resolution for upstream/combined mode must union in the FULL,
    delta-independent reference-page candidate set (batch_reference.py's own
    --rebuild-all dry-run), not just the PIA-scored HIGH/MEDIUM prose subset
    -- closing the structural gap where a real knowledge advance whose
    content generation is skipped for one cycle becomes permanently
    invisible to every later cycle's own narrower knowledge_delta.json.
    Remediation mode's explicit, operator-pinned scope must stay exactly
    unbroadened (negative control)."""

    @staticmethod
    def _write_api_surface_and_pages(tmp_path: Path) -> None:
        knowledge_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        # kind must be C#'s real tree-sitter node type ("class_declaration"),
        # matching _passes_platform_scope's platform-specific kind allowlist
        # -- the same fixture shape already proven in
        # test_verify_run_writes_content_coverage_summary above.
        (knowledge_dir / "api_surface.json").write_text(json.dumps([
            {"name": "HasPage", "kind": "class_declaration", "methods": [], "properties": [],
             "visibility": "public", "reachable": True, "file": "HasPage.cs"},
            {"name": "MissingPage", "kind": "class_declaration", "methods": [], "properties": [],
             "visibility": "public", "reachable": True, "file": "MissingPage.cs"},
        ]), encoding="utf-8")
        (knowledge_dir / "claims.json").write_text("[]", encoding="utf-8")
        (knowledge_dir / "knowledge_delta.json").write_text("{}", encoding="utf-8")
        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "net"
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "HasPage.md").write_text(
            "---\nauto_updatable: true\n---\n# HasPage\n", encoding="utf-8"
        )

    def test_upstream_scope_includes_full_reference_candidate_set(self, tmp_path: Path):
        self._write_api_surface_and_pages(tmp_path)
        manifest = refresh_run.create_run(
            "pdf", "net", mode="upstream", run_id="RUN-FULLREF-UPSTREAM", session_id="session-1",
        )
        planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-FULLREF-UPSTREAM/planning/pdf/net"
        planning.mkdir(parents=True)
        (planning / "page_impact.json").write_text(json.dumps({"pages": []}), encoding="utf-8")

        prepared = refresh_run.prepare_run(manifest)

        scope_paths = prepared["scope"]["paths"]
        # MissingPage has no page at all -- must be pinned into scope so a
        # future apply_run() actually generates it, closing G17's exact gap.
        assert "content/reference.aspose.org/en/pdf/net/MissingPage.md" in scope_paths
        # HasPage already has a page -- rebuild_all's dry-run correctly
        # reports it as "eligible for rebuild" too (the meaningful-change
        # guard, unchanged, is what keeps this from being a real rewrite at
        # apply time -- pinning it into scope is not itself a content change).
        assert "content/reference.aspose.org/en/pdf/net/HasPage.md" in scope_paths

    def test_combined_scope_includes_full_reference_candidate_set(self, tmp_path: Path):
        """Same union must apply to combined mode, not just pure upstream."""
        self._write_api_surface_and_pages(tmp_path)
        explicit = tmp_path / "scope.json"
        explicit.write_text(json.dumps(
            {"paths": ["content/docs.aspose.org/en/pdf/net/known-defect.md"]}
        ), encoding="utf-8")
        (tmp_path / "content/docs.aspose.org/en/pdf/net/known-defect.md").parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "content/docs.aspose.org/en/pdf/net/known-defect.md").write_text(
            "page\n", encoding="utf-8"
        )
        manifest = refresh_run.create_run(
            "pdf", "net", mode="combined", scope_manifest="scope.json",
            run_id="RUN-FULLREF-COMBINED", session_id="session-1",
        )
        planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-FULLREF-COMBINED/planning/pdf/net"
        planning.mkdir(parents=True)
        (planning / "page_impact.json").write_text(json.dumps({"pages": []}), encoding="utf-8")

        prepared = refresh_run.prepare_run(manifest)

        scope_paths = prepared["scope"]["paths"]
        assert "content/docs.aspose.org/en/pdf/net/known-defect.md" in scope_paths
        assert "content/reference.aspose.org/en/pdf/net/MissingPage.md" in scope_paths
        assert "content/reference.aspose.org/en/pdf/net/HasPage.md" in scope_paths

    def test_remediation_mode_scope_stays_unbroadened(self, tmp_path: Path):
        """Negative control: remediation mode's explicit, operator-pinned
        scope must NEVER be broadened by the full reference-candidate set --
        only upstream/combined mode gets that union. Proven by seeding an
        api_surface.json with a class that has no reference page yet (which
        WOULD appear in scope if the wrong branch fired) and asserting it is
        absent from the resolved scope."""
        self._write_api_surface_and_pages(tmp_path)
        explicit = "content/docs.aspose.org/en/pdf/net/known-defect.md"
        prepared = _write_scope_manifest_and_plan(
            tmp_path, [explicit], "RUN-REMEDIATION-NOBROADEN"
        )

        assert prepared["scope"]["paths"] == [explicit]
        assert "content/reference.aspose.org/en/pdf/net/MissingPage.md" not in prepared["scope"]["paths"]
        assert "content/reference.aspose.org/en/pdf/net/HasPage.md" not in prepared["scope"]["paths"]


def test_apply_run_reference_scope_always_uses_rebuild_all_confirm_rebuild(tmp_path: Path):
    """G17 deep-reassessment pass: apply_run's reference-scope call must
    ALWAYS pass --rebuild-all --confirm-rebuild, for every manifest mode --
    never falling back to --update. --update is delta-scoped (modified_apis
    only in knowledge_delta.json) and would silently exclude any class whose
    real knowledge-model addition was never propagated by a prior cycle --
    the exact G17 gap. The OLD code's conditional gave 'upstream' mode
    --update whenever removed_apis_count == 0 (the common case) -- this is
    the scenario that would have silently regressed without this test."""
    knowledge_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "api_surface.json").write_text(json.dumps([
        {"name": "HasPage", "kind": "class_declaration", "methods": [], "properties": [],
         "visibility": "public", "reachable": True, "file": "HasPage.cs"},
    ]), encoding="utf-8")
    (knowledge_dir / "claims.json").write_text("[]", encoding="utf-8")
    (knowledge_dir / "knowledge_delta.json").write_text("{}", encoding="utf-8")
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "net"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "HasPage.md").write_text(
        "---\nauto_updatable: true\n---\n# HasPage\n", encoding="utf-8"
    )

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-APPLY-REBUILDALL", session_id="session-1",
    )
    planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-APPLY-REBUILDALL/planning/pdf/net"
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    prepared = refresh_run.prepare_run(manifest)
    assert "content/reference.aspose.org/en/pdf/net/HasPage.md" in prepared["scope"]["paths"]

    recorded_calls: list = []

    def capturing_runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        str_args = [str(a) for a in args]
        if any("batch_reference.py" in a for a in str_args):
            recorded_calls.append(str_args)
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-APPLY-REBUILDALL"
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-APPLY-REBUILDALL",
                    "page_path": "content/reference.aspose.org/en/pdf/net/HasPage.md",
                    "disposition": "REFERENCE_UNCHANGED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=capturing_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(prepared)

    assert result["state"] == "VALIDATING"
    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    assert "--rebuild-all" in call
    assert "--confirm-rebuild" in call
    assert "--update" not in call


def test_prepare_run_post_kr_diff_uses_generous_timeout(tmp_path: Path):
    """Found live 2026-08-24 (mission-plan-the-end-to-end-vast-hejlsberg.md
    Task 14): prepare_run's own post-knowledge-refresh 'git diff --name-only
    <base>' call is a deliberate WHOLE-WORKING-TREE diff (no path scoping),
    unlike every other git call in this module -- its cost scales with the
    repo's total dirty-file count, not this run's own scope. Measured live
    against a real, unrelated concurrent-session sweep (~2,100 dirty files,
    ~164k tracked files, Windows core.autocrlf re-normalization overhead):
    ~50s, past the 30s timeout every other single-path/graph-only call in
    this module correctly uses. This pins the fix (180s) so it can't
    silently regress back to a value too tight for a real, documented,
    non-rare occurrence in this repo (CLAUDE.md's own ST-021 note)."""
    TestFullReferenceScopeResolution._write_api_surface_and_pages(tmp_path)

    recorded_timeouts: list = []

    def _runner_recording_diff_timeout(args: list[str], **kwargs: object):
        if args[:3] == ["git", "diff", "--name-only"]:
            recorded_timeouts.append(kwargs.get("timeout"))
        return _runner(args, **kwargs)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=_runner_recording_diff_timeout,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-POSTKR-TIMEOUT", session_id="session-1",
    )
    planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-POSTKR-TIMEOUT/planning/pdf/net"
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(json.dumps({"pages": []}), encoding="utf-8")

    refresh_run.prepare_run(manifest)

    assert recorded_timeouts == [180]


def test_upstream_scope_still_zero_when_pia_finds_nothing_affected(tmp_path: Path):
    """Negative control: a real PIA report with ONLY LOW_IMPACT/NOT_AFFECTED
    pages must still correctly raise -- the fix above must not become a
    blanket bypass of the zero-scope guard."""
    low = "content/docs.aspose.org/en/pdf/net/low.md"
    not_affected = "content/docs.aspose.org/en/pdf/net/not-affected.md"
    for relative in (low, not_affected):
        page = tmp_path / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("page\n", encoding="utf-8")

    delta_path = tmp_path / "knowledge/pdf/net/merged/knowledge_delta.json"
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text("{}", encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-PIA-EMPTY",
        session_id="session-1",
    )
    planning = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-PIA-EMPTY/planning/pdf/net"
    )
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"path": low, "pia_score": "LOW_IMPACT"},
                    {"path": not_affected, "pia_score": "NOT_AFFECTED"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(refresh_run.RefreshRunError, match="zero pages"):
        refresh_run.prepare_run(manifest)


def test_illegal_transition_is_rejected():
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-TRANSITION",
        session_id="session-1",
    )
    with pytest.raises(refresh_run.RefreshRunError, match="Illegal"):
        refresh_run._transition(manifest, "COMMITTED")


def test_second_active_run_for_product_is_rejected():
    refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-FIRST",
        session_id="session-1",
    )
    with pytest.raises(refresh_run.RefreshRunError, match="already has active run"):
        refresh_run.create_run(
            "pdf",
            "net",
            mode="upstream",
            run_id="RUN-SECOND",
            session_id="session-2",
        )


def test_explicit_run_id_is_globally_unique(tmp_path: Path):
    refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-GLOBAL",
        session_id="session-1",
    )
    other_model = tmp_path / "knowledge/cells/java/merged/model.yaml"
    other_model.parent.mkdir(parents=True)
    other_model.write_text(
        yaml.safe_dump(
            {
                "family": "cells",
                "platform": "java",
                "repo_sha": MODEL_SHA,
                "stale_since": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(refresh_run.RefreshRunError, match="already exists"):
        refresh_run.create_run(
            "cells",
            "java",
            mode="upstream",
            run_id="RUN-GLOBAL",
            session_id="session-2",
        )


def test_abandon_is_terminal_and_clears_active_pointer(tmp_path: Path):
    refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ABANDON",
        session_id="session-1",
    )
    manifest = refresh_run.abandon_run(
        "pdf",
        "net",
        "RUN-ABANDON",
        reason="operator cancelled before content mutation",
        session_id="session-1",
    )
    assert manifest["state"] == "ABANDONED"
    assert not (tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json").exists()


def test_abandon_restores_working_tree_to_pinned_baseline(tmp_path: Path):
    """RPR-ABANDON-001: abandon_run() must restore the working tree to the
    pinned baseline the same way recover_run() already does -- before this
    fix, abandon_run only transitioned state and cleared the active pointer,
    leaving whatever body_refresh.py had already written on disk. Real
    production evidence (FONT-PYTHON-REFRESH-002, backlog/BACKLOG.md) shows
    corruption compounded across repeated abandon+restart cycles specifically
    because abandon left the tree dirty and the next attempt started from
    it, not from a clean baseline. This mirrors
    test_recover_restores_only_receipt_owned_output_and_abandons exactly,
    substituting abandon_run for recover_run, to prove both verbs now give
    the same safety guarantee.
    """
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"
    base_content = "---\ntitle: Base\n---\n\nOriginal body.\n"
    output_content = "---\ntitle: Base\n---\n\nRun output.\n"

    def recovery_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:3] == ["git", "cat-file", "--filters"]:
            return subprocess.CompletedProcess(args, 0, base_payload, b"")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=recovery_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    page = tmp_path / page_path
    page.parent.mkdir(parents=True)
    page.write_text(base_content, encoding="utf-8")
    base_payload = page.read_bytes()
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ABANDON-RESTORE",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    _replace_synthetic_output(
        tmp_path,
        manifest,
        page_path=page_path,
        content=output_content,
    )
    refresh_run._transition(manifest, "VALIDATING")

    # page currently holds output_content -- exactly what body_refresh.py's
    # own writer produced and receipted for this run (the real incident
    # shape: the run's OWN recorded output is what needs rolling back, not
    # some unrelated third-party edit -- that separate case is already
    # covered by test_recover_refuses_scoped_path_changed_after_run_output).
    abandoned = refresh_run.abandon_run(
        "pdf",
        "net",
        "RUN-ABANDON-RESTORE",
        reason="body_refresh.py's output for this run must be rolled back",
        session_id="session-1",
    )

    assert abandoned["state"] == "ABANDONED"
    assert page.read_bytes() == base_payload, (
        "abandon must restore the working tree to the pinned baseline, "
        "not leave the run's own output on disk"
    )
    assert abandoned["recovery"]["restored_paths"] == [page_path]
    assert not (
        tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json"
    ).exists()


def test_abandon_before_any_output_is_a_safe_noop(tmp_path: Path):
    """Abandoning a run before APPLYING ever produced page_decisions.jsonl
    must remain a harmless no-op restore, not an error -- this is the exact
    shape test_abandon_is_terminal_and_clears_active_pointer already
    exercises; this test makes the no-op restore behavior explicit."""
    refresh_run.configure(repo_root=tmp_path, command_runner=_runner)
    refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ABANDON-EARLY",
        session_id="session-1",
    )
    manifest = refresh_run.abandon_run(
        "pdf",
        "net",
        "RUN-ABANDON-EARLY",
        reason="cancelled before any content mutation",
        session_id="session-1",
    )
    assert manifest["state"] == "ABANDONED"
    assert manifest["recovery"]["restored_paths"] == []
    assert not (tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json").exists()


def test_abandon_succeeds_even_when_evidence_digests_are_unverifiable(tmp_path: Path):
    """Independent-review finding: a crash mid-APPLYING can leave
    page_decisions.jsonl partially written on disk while
    manifest["output_digests"] was never finalized (that only happens at the
    end of apply_run) -- _assert_run_evidence_ready's digest check correctly
    can't verify evidence integrity in that window, but abandon_run must
    still succeed unconditionally: it is the last-resort "give up" verb, and
    every retry would otherwise hit the identical digest-mismatch error with
    no way to ever clear the run. recover_run (an explicit, deliberate
    operator action) is allowed to keep failing loudly here by design --
    only abandon_run must degrade to a best-effort, unverified restore.
    """
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"
    refresh_run.configure(repo_root=tmp_path, command_runner=_runner)
    page = tmp_path / page_path
    page.parent.mkdir(parents=True)
    page.write_text("---\ntitle: Test\n---\n\nBody.\n", encoding="utf-8")
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ABANDON-CRASH",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)

    # Simulate a crash: page_decisions.jsonl is really on disk (written just
    # above), but the manifest's own output_digests were never finalized --
    # that only happens once apply_run completes normally.
    manifest["output_digests"]["page_decisions"] = None
    refresh_run._save_manifest(manifest)

    abandoned = refresh_run.abandon_run(
        "pdf",
        "net",
        "RUN-ABANDON-CRASH",
        reason="crashed mid-apply, giving up",
        session_id="session-1",
    )
    assert abandoned["state"] == "ABANDONED"
    assert abandoned["recovery"]["restored_paths"] == []
    assert "restore_error" in abandoned["recovery"]
    assert not (tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json").exists()


def test_abandon_succeeds_on_non_refresh_run_error_during_restore(tmp_path: Path):
    """Independent-review finding #2: abandon's "never gets stuck" guarantee
    must hold for ANY failure inside _restore_scope_to_baseline, not just
    RefreshRunError. A hung/failing git subprocess fetching the pinned-base
    bytes (`git cat-file --filters`) is exactly this: it runs only after
    every digest/hash precondition in _assert_run_evidence_ready has already
    passed (confirmed empirically -- corrupting scope.json or a receipt's
    *content* while keeping their recorded digests consistent still gets
    caught by _assert_pinned_scope's own RefreshRunError wrapping or the
    per-row receipt_digest check first, never reaching this deep), so it is
    the cleanest real place a genuinely unwrapped exception
    (subprocess.TimeoutExpired in production; a plain OSError here, which is
    equally uncaught by the pre-broadening `except RefreshRunError`) can
    occur, and abandon must still not get stuck when it does.
    """
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"
    base_content = "---\ntitle: Base\n---\n\nOriginal body.\n"
    output_content = "---\ntitle: Base\n---\n\nRun output.\n"

    def hanging_git_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:3] == ["git", "cat-file", "--filters"]:
            raise OSError("git process did not respond (simulated hang)")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=hanging_git_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    page = tmp_path / page_path
    page.parent.mkdir(parents=True)
    page.write_text(base_content, encoding="utf-8")
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ABANDON-GITHANG",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    _replace_synthetic_output(
        tmp_path, manifest, page_path=page_path, content=output_content,
    )
    refresh_run._transition(manifest, "VALIDATING")

    abandoned = refresh_run.abandon_run(
        "pdf",
        "net",
        "RUN-ABANDON-GITHANG",
        reason="git hung fetching pinned base, giving up anyway",
        session_id="session-1",
    )
    assert abandoned["state"] == "ABANDONED"
    assert abandoned["recovery"]["restored_paths"] == []
    assert "restore_error" in abandoned["recovery"]
    assert "simulated hang" in abandoned["recovery"]["restore_error"]
    assert not (tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json").exists()


def test_abandon_deletes_a_generated_page_absent_from_the_pinned_base(tmp_path: Path):
    """RPR-ABANDON-002 (found live 2026-08-25, pdf/java's Task 14 upstream
    proof run): a GENERATED-disposition page (e.g. G17's full-reference-scope
    rebuild creating a brand-new reference page) has no initial_hash entry
    corresponding to real base-commit bytes -- initial_hashes records
    "MISSING" for it (the same sentinel _path_hash returns for a nonexistent
    file). Restoring to baseline for such a page means DELETING it, not
    fetching a non-existent blob via `git cat-file` against the pinned base
    commit (which always fails for a path absent from that commit) -- the
    pre-fix code raised RefreshRunError unconditionally here, and because
    that raise happened mid-validation-loop, abandon_run's own outer
    try/except (which must never let abandon get stuck) degraded the WHOLE
    restore to 0/0, discarding even other rows already validated -- exactly
    the "silently reported 0/0" symptom hit live twice on two separate
    abandoned runs this same session, both after a real G17 full rebuild had
    generated hundreds of new pages."""
    page_path = "content/reference.aspose.org/en/pdf/net/NewClass.md"
    refresh_run.configure(repo_root=tmp_path, command_runner=_runner)
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ABANDON-GENERATED",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(
        tmp_path, manifest, dispositions={page_path: "GENERATED"},
    )
    # Override the fixture's own placeholder-content bookkeeping: a truly
    # GENERATED page never existed at scope-pin time, so its initial_hashes
    # entry is "MISSING" (the same sentinel _path_hash returns for an absent
    # file), not the hash of whatever placeholder body _write_run_evidence
    # had to write to compute a receipt at all.
    run_root = (
        tmp_path / "reports/refresh_runs" / manifest["family"]
        / manifest["platform"] / manifest["run_id"]
    )
    scope_path = run_root / "scope.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope["initial_hashes"][page_path] = "MISSING"
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    manifest["output_digests"]["scope"] = refresh_run._file_digest(scope_path)
    refresh_run._save_manifest(manifest)
    refresh_run._transition(manifest, "VALIDATING")

    assert (tmp_path / page_path).is_file()

    abandoned = refresh_run.abandon_run(
        "pdf",
        "net",
        "RUN-ABANDON-GENERATED",
        reason="giving up, page should be deleted not restored",
        session_id="session-1",
    )
    assert abandoned["state"] == "ABANDONED"
    assert "restore_error" not in abandoned["recovery"]
    assert abandoned["recovery"]["restored_paths"] == [page_path]
    assert not (tmp_path / page_path).exists()
    assert not (tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json").exists()


def test_abandon_with_mixed_generated_and_preexisting_pages_restores_both(
    tmp_path: Path,
):
    """A single abandon must correctly handle a GENERATED page (delete) and
    a genuinely pre-existing page (restore-to-content) together in the same
    run -- the realistic G17 shape (a full rebuild mixes new and updated
    pages in one scope), and a regression guard against a fix that only
    handles the loop's first or last row correctly."""
    generated_path = "content/reference.aspose.org/en/pdf/net/NewClass.md"
    existing_path = "content/reference.aspose.org/en/pdf/net/OldClass.md"
    base_payload_holder: dict[str, bytes] = {}

    def mixed_runner(args: list[str], **_: object) -> subprocess.CompletedProcess:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:3] == ["git", "cat-file", "--filters"]:
            return subprocess.CompletedProcess(
                args, 0, base_payload_holder["existing"], b"",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(repo_root=tmp_path, command_runner=mixed_runner)
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ABANDON-MIXED",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [generated_path, existing_path]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(
        tmp_path,
        manifest,
        dispositions={generated_path: "GENERATED", existing_path: "BODY_UPDATED"},
    )
    # Capture the exact bytes _write_run_evidence actually wrote for the
    # pre-existing page (its own placeholder-content write is subject to
    # the same platform newline-translation behavior real writers are --
    # reading it back, rather than re-encoding a literal string, keeps the
    # mocked `git cat-file --filters` response byte-identical to what
    # initial_hashes[existing_path] was actually computed from).
    base_payload_holder["existing"] = (tmp_path / existing_path).read_bytes()
    run_root = (
        tmp_path / "reports/refresh_runs" / manifest["family"]
        / manifest["platform"] / manifest["run_id"]
    )
    scope_path = run_root / "scope.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope["initial_hashes"][generated_path] = "MISSING"
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    manifest["output_digests"]["scope"] = refresh_run._file_digest(scope_path)
    refresh_run._save_manifest(manifest)
    _replace_synthetic_output(
        tmp_path, manifest, page_path=existing_path,
        content="---\ntitle: Test\n---\n\nUpdated body.\n",
    )
    refresh_run._transition(manifest, "VALIDATING")

    abandoned = refresh_run.abandon_run(
        "pdf",
        "net",
        "RUN-ABANDON-MIXED",
        reason="giving up on a mixed generated+existing scope",
        session_id="session-1",
    )
    assert abandoned["state"] == "ABANDONED"
    assert "restore_error" not in abandoned["recovery"]
    assert sorted(abandoned["recovery"]["restored_paths"]) == sorted(
        [generated_path, existing_path]
    )
    assert not (tmp_path / generated_path).exists()
    assert (tmp_path / existing_path).read_text(encoding="utf-8") == (
        "---\ntitle: Test\n---\n\nGrounded body.\n"
    )


def test_owner_mismatch_blocks_mutation():
    refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-OWNER",
        session_id="session-1",
    )
    with pytest.raises(refresh_run.RefreshRunError, match="owned by session"):
        refresh_run.execute_run(
            "pdf",
            "net",
            "RUN-OWNER",
            session_id="session-2",
            dry_run=True,
        )


def test_cli_status_is_read_only_and_does_not_require_identity(capsys):
    refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-STATUS",
        session_id="session-1",
    )
    assert refresh_run.main(["status", "--run-id", "RUN-STATUS"]) == 0
    assert '"state": "INPUTS_PINNED"' in capsys.readouterr().out


def _write_scope_manifest_and_plan(tmp_path: Path, paths: list[str], run_id: str):
    """Shared setup: real files on disk, a remediation-mode scope manifest,
    and a PLANNED manifest with real initial_hashes (via prepare_run)."""
    for relative in paths:
        page = tmp_path / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("original\n", encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"paths": paths}), encoding="utf-8")
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="remediation",
        scope_manifest="scope.json",
        run_id=run_id,
        session_id="session-1",
    )
    prepared = refresh_run.prepare_run(manifest)
    body_impact = (
        tmp_path / "reports/refresh_runs/pdf/net" / run_id / "planning/pdf/net"
    )
    body_impact.mkdir(parents=True, exist_ok=True)
    (body_impact / "body_impact.json").write_text("[]", encoding="utf-8")
    return prepared


def test_apply_reconciliation_tolerates_no_op_skip_and_out_of_scope_advisory_rows(
    tmp_path: Path,
):
    """Regression test for a confirmed bug: apply_run() required an EXACT
    set match between scope_paths and page_decisions.jsonl's page_path
    values. Found live (MT014-2026-07-29-PDF-GO-REDO): body_refresh.py has
    early-exit paths (auto_updatable:false pages; pages with zero actionable
    BODY_UPDATE sections) that never call _emit_run_decision, so a scoped
    no-op page legitimately has no decision row; and batch_reference.py's
    --update mode logs a disposition for every class in knowledge_delta.json,
    not just the ones this run's scope selected, so out-of-scope
    NOT_AFFECTED rows are expected noise, not a violation -- --run-root
    already restricts actual file WRITES to scope. Fix: only treat a
    "missing" scoped page as a real problem if its bytes actually changed
    from the initial_hashes snapshot frozen at PLANNED time, and only treat
    an "unexpected" out-of-scope row as a real problem if its disposition
    implies a write happened."""
    structural = "content/docs.aspose.org/en/pdf/net/structural.md"
    updated = "content/docs.aspose.org/en/pdf/net/updated.md"
    manifest = _write_scope_manifest_and_plan(
        tmp_path, [structural, updated], "RUN-RECONCILE-OK"
    )

    from commands.content.body_refresh import _normalized_body_hash
    empty_hash = _normalized_body_hash("")

    def body_refresh_runner(args: list[str], **_: object):
        if any("body_refresh.py" in str(a) for a in args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-RECONCILE-OK"
            (tmp_path / updated).write_text("changed\n", encoding="utf-8")
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-RECONCILE-OK",
                    "page_path": updated,
                    "disposition": "BODY_UPDATED",
                }) + "\n")
                # structural.md: no row at all (simulates an early-exit skip)
                # unrelated.md: out-of-scope advisory row, no disposition
                # implying a write -- must not be treated as a violation.
                f.write(json.dumps({
                    "run_id": "RUN-RECONCILE-OK",
                    "page_path": "content/docs.aspose.org/en/pdf/net/unrelated.md",
                    "disposition": "NOT_AFFECTED",
                }) + "\n")
                # new-class.md: out-of-scope GENERATED row for a page that
                # provably did not exist before (empty body_hash_before) --
                # an additive write, must not be treated as a violation
                # (batch_reference.py's --update mode generates every new
                # class in knowledge_delta.json, not just scoped ones).
                f.write(json.dumps({
                    "run_id": "RUN-RECONCILE-OK",
                    "page_path": "content/reference.aspose.org/en/pdf/net/NewClass.md",
                    "disposition": "GENERATED",
                    "body_hash_before": empty_hash,
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=body_refresh_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)  # must not raise
    assert result["state"] == "VALIDATING"


def test_apply_reconciliation_still_blocks_real_violations(tmp_path: Path):
    """Negative control: the fix above must not become a blanket bypass --
    a scoped page silently mutated with NO decision row, and an out-of-scope
    page with a write-implying disposition, must both still raise."""
    silent = "content/docs.aspose.org/en/pdf/net/silent.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [silent], "RUN-RECONCILE-BAD")

    def bad_runner(args: list[str], **_: object):
        if any("body_refresh.py" in str(a) for a in args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-RECONCILE-BAD"
            # Silently mutate the page with NO decision row at all.
            (tmp_path / silent).write_text("silently changed\n", encoding="utf-8")
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                # An out-of-scope page claiming a real write -- a genuine
                # scope violation, must still be caught.
                f.write(json.dumps({
                    "run_id": "RUN-RECONCILE-BAD",
                    "page_path": "content/docs.aspose.org/en/pdf/net/out-of-scope.md",
                    "disposition": "GENERATED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=bad_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    with pytest.raises(refresh_run.RefreshRunError, match="reconciliation failed"):
        refresh_run.apply_run(manifest)


def test_apply_reconciliation_blocks_generated_over_existing_content(tmp_path: Path):
    """Negative control, narrower than the one above: a GENERATED row for an
    out-of-scope page whose body_hash_before is explicitly non-empty (proof
    it HAD real pre-existing content) must still block -- the additive-write
    exception only covers provably-new pages, not a mislabeled overwrite."""
    silent = "content/docs.aspose.org/en/pdf/net/silent.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [silent], "RUN-RECONCILE-OVERWRITE")

    def bad_runner(args: list[str], **_: object):
        if any("body_refresh.py" in str(a) for a in args):
            run_root = (
                tmp_path / "reports/refresh_runs/pdf/net/RUN-RECONCILE-OVERWRITE"
            )
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-RECONCILE-OVERWRITE",
                    "page_path": "content/reference.aspose.org/en/pdf/net/Existing.md",
                    "disposition": "GENERATED",
                    "body_hash_before": "sha256:" + "1" * 64,
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=bad_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    with pytest.raises(refresh_run.RefreshRunError, match="reconciliation failed"):
        refresh_run.apply_run(manifest)


# ---------------------------------------------------------------------------
# TC12 (2026-08-21, backlink-governance-redesign): apply_run()'s new
# backlink-reconciliation writer step. This is the mission's own mandatory
# acceptance criterion: "An end-to-end test proves refresh-product repairs a
# deliberately-broken backlink on a fixture product across all 5 subdomains,
# not just reference.aspose.org." The scope here is docs.aspose.org --
# confirmed by this mission's own research to be one of the 4 subdomains
# refresh-product previously never touched at all for backlinks.
# ---------------------------------------------------------------------------

def test_apply_run_reconciles_backlink_outside_reference_subdomain(tmp_path: Path):
    """The core repeatability fix: a docs.aspose.org page with a WRONG
    aspose.com backlink gets corrected by apply_run()'s new step, even
    though nothing about this page's content (body_refresh.py's own scope)
    needed changing -- proving backlink correctness no longer depends on
    reference.aspose.org's side-effect-only coverage."""
    broken = "content/docs.aspose.org/en/pdf/net/getting-started.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [broken], "RUN-BACKLINK-FIX")
    corrected_text = "---\ntitle: Getting Started\n---\n\nFixed body with correct link.\n"

    def runner(args: list[str], **_: object):
        str_args = [str(a) for a in args]
        if any("body_refresh.py" in a for a in str_args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-BACKLINK-FIX"
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-BACKLINK-FIX",
                    "page_path": broken,
                    "disposition": "NOT_AFFECTED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        if "backlink_backfill.py" in " ".join(str_args):
            # Simulate the real tool: writes the corrected page for real,
            # and reports it as a non-skipped change in its output manifest.
            (tmp_path / broken).write_text(corrected_text, encoding="utf-8")
            out_path = Path(str_args[str_args.index("--output") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps({
                "generated_at": "2026-07-25T00:00:00+00:00",
                "generator": "test-stub", "dry_run": False,
                "total_candidates": 1, "total_modified": 1,
                "total_skipped": 0, "total_errors": 0,
                "changes": [{
                    "file": broken, "subdomain": "docs.aspose.org",
                    "family": "pdf", "platform": "net", "page_type": "docs-article",
                    "target_url": "https://docs.aspose.com/pdf/net/",
                    "action": "md_see_also", "before_snippet": "", "after_snippet": "",
                    "skipped": False, "skip_reason": "", "dry_run": False,
                    "warning_messages": [],
                }],
                "errors": [], "rollback_commands": [],
            }), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)
    assert result["state"] == "VALIDATING"
    # The writer step's effect actually landed on disk.
    assert (tmp_path / broken).read_text(encoding="utf-8") == corrected_text
    # The later OCC guard in verify_run() (_assert_scope_ownership) would
    # otherwise block on this out-of-band write, since backlink_backfill.py
    # emits no page_decisions.jsonl row for it -- confirm
    # _record_extra_allowed_hash() actually registered it, the same sidecar
    # mechanism already proven for the TC-DUPIDX-02 index step.
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-BACKLINK-FIX"
    extra_hashes = json.loads(
        (run_root / "extra_allowed_hashes.json").read_text(encoding="utf-8")
    )
    assert broken in extra_hashes
    # Hash the actual bytes on disk (not the in-memory string) -- Path.write_text()
    # applies platform newline translation, so this avoids a spurious \n vs \r\n mismatch.
    expected_hash = "sha256:" + hashlib.sha256((tmp_path / broken).read_bytes()).hexdigest()
    assert expected_hash in extra_hashes[broken]


def test_apply_run_backlink_reconciliation_passes_deep_flag(tmp_path: Path):
    """TC15-F1 (found live 2026-08-26): apply_run()'s backlink_backfill.py
    invocation must pass --deep. Without it, resolve_backlink() has no
    access to the pre-approved deep-authority index, so a
    reference.aspose.org class page with no simple same-section
    family-level target resolves BLOCKED_TARGET and is silently skipped
    instead of repaired -- confirmed live: commit ea05b9d8c8 ran a real
    batch_reference.py --rebuild-all regeneration of
    reference.aspose.org/pdf/java through this exact apply_run() path,
    stripping 247 pages' backlinks; this reconciliation step ran
    immediately afterward in the same commit specifically to catch that
    drift, and (without --deep) silently let all 247 through as
    BLOCKED_TARGET instead of repairing them. Reproduced directly:
    `backlink_backfill.py --family pdf --platform java` (no --deep)
    dry-runs to 0 modified / 1194 BLOCKED_TARGET; the identical call with
    --deep dry-runs to 247 modified, matching the live regression count."""
    broken = "content/docs.aspose.org/en/pdf/net/getting-started.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [broken], "RUN-BACKLINK-DEEP")
    invoked_args: list[str] = []

    def runner(args: list[str], **_: object):
        str_args = [str(a) for a in args]
        if any("body_refresh.py" in a for a in str_args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-BACKLINK-DEEP"
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-BACKLINK-DEEP",
                    "page_path": broken,
                    "disposition": "NOT_AFFECTED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        if "backlink_backfill.py" in " ".join(str_args):
            invoked_args.extend(str_args)
            out_path = Path(str_args[str_args.index("--output") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps({
                "generated_at": "2026-07-25T00:00:00+00:00",
                "generator": "test-stub", "dry_run": False,
                "total_candidates": 0, "total_modified": 0,
                "total_skipped": 0, "total_errors": 0,
                "changes": [], "errors": [], "rollback_commands": [],
            }), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)
    assert result["state"] == "VALIDATING"
    assert "--deep" in invoked_args


def test_apply_run_backlink_reconciliation_reports_page_errors(tmp_path: Path):
    """Negative control: backlink_backfill.py's own CLI always exits 0 even
    when manifest.errors is non-empty (confirmed live) -- apply_run() must
    explicitly inspect total_errors and raise, not trust the exit code alone."""
    broken = "content/docs.aspose.org/en/pdf/net/broken.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [broken], "RUN-BACKLINK-ERR")

    def runner(args: list[str], **_: object):
        str_args = [str(a) for a in args]
        if any("body_refresh.py" in a for a in str_args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-BACKLINK-ERR"
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-BACKLINK-ERR",
                    "page_path": broken,
                    "disposition": "NOT_AFFECTED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        if "backlink_backfill.py" in " ".join(str_args):
            out_path = Path(str_args[str_args.index("--output") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps({
                "generated_at": "2026-07-25T00:00:00+00:00",
                "generator": "test-stub", "dry_run": False,
                "total_candidates": 1, "total_modified": 0,
                "total_skipped": 0, "total_errors": 1,
                "changes": [],
                "errors": [{"file": broken, "error": "YAML round-trip failure"}],
                "rollback_commands": [],
            }), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")  # exit 0, per real tool
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    with pytest.raises(refresh_run.RefreshRunError, match="backlink reconciliation reported"):
        refresh_run.apply_run(manifest)


# ---------------------------------------------------------------------------
# TC-CONTENTHASH-01 (found live 2026-08-25, TC12 backlink-governance-redesign
# real end-to-end proof exercise -- a genuine refresh-product remediation run
# against a real fixture product, through the real CLI, ending in a real
# `git commit`): none of apply_run()'s three writers (body_refresh.py,
# batch_reference.py, backlink_backfill.py) update `provenance.content_hash`
# themselves. The pre-commit hook's own content_hash normalization step
# (provenance_normalize_hash.py, universal -- fires on every commit whose
# stored content_hash no longer matches the body) mutates a committed file's
# bytes strictly AFTER apply_run() has already pinned every hash
# bind_commit()'s OCC guard (_assert_scope_ownership) will later accept.
# This unconditionally rejected the resulting commit -- "Scoped working
# files changed outside a validated run checkpoint" -- confirmed live on a
# real refresh-product run (tc12-proof-02) even though the ONLY additional
# change was the pre-commit hook's own expected, routine fix. TC12's own
# test suite never caught this because it calls apply_run() directly and
# never runs a real `git commit` through the real pre-commit hook chain.
# ---------------------------------------------------------------------------

def test_apply_run_normalizes_content_hash_for_occ_guard(tmp_path: Path):
    """apply_run() must self-normalize content_hash on every path it
    touched (scoped or extra-allowed) as its own last step, so a later,
    routine pre-commit-hook content_hash fix is a true no-op and
    bind_commit()'s OCC guard already recognizes the final committed
    bytes."""
    broken = "content/kb.aspose.org/en/pdf/net/faq.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [broken], "RUN-CONTENTHASH")

    stale_hash = "0" * 32  # deliberately wrong -- never matches any real body
    corrected_text = (
        "---\ntitle: Test\nprovenance:\n"
        f"  content_hash: {stale_hash}\n---\ncorrected body\n"
    )
    page = tmp_path / broken

    def runner(args: list[str], **_: object):
        str_args = [str(a) for a in args]
        if any("body_refresh.py" in a for a in str_args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-CONTENTHASH"
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-CONTENTHASH",
                    "page_path": broken,
                    "disposition": "NOT_AFFECTED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        if "backlink_backfill.py" in " ".join(str_args):
            # Simulate the real tool: rewrites the body for real, but --
            # like the real backlink_backfill.py -- never touches
            # content_hash, leaving it stale relative to the new body.
            page.write_text(corrected_text, encoding="utf-8")
            out_path = Path(str_args[str_args.index("--output") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps({
                "generated_at": "2026-07-25T00:00:00+00:00",
                "generator": "test-stub", "dry_run": False,
                "total_candidates": 1, "total_modified": 1,
                "total_skipped": 0, "total_errors": 0,
                "changes": [{
                    "file": broken, "subdomain": "kb.aspose.org",
                    "family": "pdf", "platform": "net", "page_type": "kb-article",
                    "target_url": "https://kb.aspose.com/pdf/net/",
                    "action": "md_see_also", "before_snippet": "", "after_snippet": "",
                    "skipped": False, "skip_reason": "", "dry_run": False,
                    "warning_messages": [],
                }],
                "errors": [], "rollback_commands": [],
            }), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)
    assert result["state"] == "VALIDATING"

    from lib.provenance import compute_content_hash, read_provenance

    prov = read_provenance(page)
    actual_hash = compute_content_hash(page)
    # The bug: without the fix, prov["content_hash"] stays == stale_hash.
    assert prov["content_hash"] == actual_hash
    assert prov["content_hash"] != stale_hash

    # The OCC guard must already recognize the final (post-normalization)
    # bytes, not just the pre-normalization ones apply_run() first recorded.
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-CONTENTHASH"
    extra_hashes = json.loads(
        (run_root / "extra_allowed_hashes.json").read_text(encoding="utf-8")
    )
    final_hash = "sha256:" + hashlib.sha256(page.read_bytes()).hexdigest()
    assert final_hash in extra_hashes[broken]


def test_apply_run_normalizes_crlf_for_occ_guard(tmp_path: Path):
    """Regression for the CRLF/LF root cause found in the same live proof
    exercise: this repo's own `.gitattributes` forces `content/** text
    eol=lf`, so git always commits content pages with LF endings regardless
    of what's on disk -- but `_path_hash()` hashes raw disk bytes. A writer
    that leaves CRLF on disk (confirmed live: a real committed
    content/kb.aspose.org page's working-tree bytes hashed differently from
    `git cat-file --filters` at that same commit for byte-identical text)
    makes apply_run()'s own registered hash permanently unable to match
    what bind_commit() will ever see once git normalizes on commit.
    apply_run() must normalize CRLF->LF on every touched path itself,
    matching what git will do anyway, so the two hashes agree."""
    broken = "content/kb.aspose.org/en/pdf/net/faq.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [broken], "RUN-CRLF")

    # Simulate the real tool writing CRLF line endings (confirmed live:
    # Windows-authored content commonly does), never normalized by any
    # writer in this chain.
    corrected_text = "---\r\ntitle: Test\r\n---\r\ncorrected body\r\nsecond line\r\n"
    page = tmp_path / broken

    def runner(args: list[str], **_: object):
        str_args = [str(a) for a in args]
        if any("body_refresh.py" in a for a in str_args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-CRLF"
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": "RUN-CRLF",
                    "page_path": broken,
                    "disposition": "NOT_AFFECTED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        if "backlink_backfill.py" in " ".join(str_args):
            with open(page, "wb") as f:
                f.write(corrected_text.encode("utf-8"))
            out_path = Path(str_args[str_args.index("--output") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps({
                "generated_at": "2026-07-25T00:00:00+00:00",
                "generator": "test-stub", "dry_run": False,
                "total_candidates": 1, "total_modified": 1,
                "total_skipped": 0, "total_errors": 0,
                "changes": [{
                    "file": broken, "subdomain": "kb.aspose.org",
                    "family": "pdf", "platform": "net", "page_type": "kb-article",
                    "target_url": "https://kb.aspose.com/pdf/net/",
                    "action": "md_see_also", "before_snippet": "", "after_snippet": "",
                    "skipped": False, "skip_reason": "", "dry_run": False,
                    "warning_messages": [],
                }],
                "errors": [], "rollback_commands": [],
            }), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)
    assert result["state"] == "VALIDATING"

    final_bytes = page.read_bytes()
    # The bug: without the fix, final_bytes still contains b"\r\n".
    assert b"\r\n" not in final_bytes
    assert final_bytes == corrected_text.replace("\r\n", "\n").encode("utf-8")

    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-CRLF"
    extra_hashes = json.loads(
        (run_root / "extra_allowed_hashes.json").read_text(encoding="utf-8")
    )
    final_hash = "sha256:" + hashlib.sha256(final_bytes).hexdigest()
    assert final_hash in extra_hashes[broken]


def _write_index_provenance(
    tmp_path: Path, family: str, platform: str, *,
    index_generator_version: int | None = None,
    last_mechanism: str = "skill",
) -> Path:
    """Write a reference _index.md with controllable provenance for the
    TC-DUPIDX-02 generator-version re-invocation tests below."""
    index_path = (
        tmp_path / "content/reference.aspose.org/en" / family / platform / "_index.md"
    )
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", "provenance:", f"  last_mechanism: {last_mechanism}", "  auto_updatable: true"]
    if index_generator_version is not None:
        lines.append(f"  index_generator_version: {index_generator_version}")
    lines += ["---", "", "## Core API", ""]
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def _reference_scope_runner_recording_generate_index(
    tmp_path: Path, run_id: str, scoped_path: str, calls: list,
):
    """Shared command_runner for the three TC-DUPIDX-02 tests below: satisfies the
    ordinary 'reference refresh' (--update/--rebuild-all) call with a page decision
    row for the scoped page, and separately records any --generate-index invocation
    (the new version-gated re-invocation step) without executing it for real."""
    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if any("--generate-index" in str(a) for a in args):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        if any("batch_reference.py" in str(a) for a in args):
            run_root = tmp_path / "reports/refresh_runs/pdf/net" / run_id
            with open(run_root / "page_decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "run_id": run_id,
                    "page_path": scoped_path,
                    "disposition": "GENERATED",
                }) + "\n")
            return subprocess.CompletedProcess(args, 0, "", "")
        return _runner(args)
    return runner


def test_apply_run_reinvokes_generate_grouped_index_for_stale_index_version(
    tmp_path: Path,
):
    # No index_generator_version stamp at all -- simulates every one of the 9
    # currently-published reference-index pages this taskcard's backfill targets.
    scoped = "content/reference.aspose.org/en/pdf/net/SomeClass.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [scoped], "RUN-GENIDX-STALE")
    _write_index_provenance(tmp_path, "pdf", "net", index_generator_version=None)

    generate_index_calls: list = []
    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=_reference_scope_runner_recording_generate_index(
            tmp_path, "RUN-GENIDX-STALE", scoped, generate_index_calls,
        ),
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)
    assert result["state"] == "VALIDATING"
    assert len(generate_index_calls) == 1
    call = [str(a) for a in generate_index_calls[0]]
    assert "pdf" in call and "net" in call
    assert any("batch_reference.py" in a for a in call)


def test_apply_run_skips_generate_grouped_index_when_version_current(tmp_path: Path):
    scoped = "content/reference.aspose.org/en/pdf/net/SomeClass.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [scoped], "RUN-GENIDX-CURRENT")
    _write_index_provenance(
        tmp_path, "pdf", "net",
        index_generator_version=GROUPED_INDEX_GENERATOR_VERSION,
    )

    generate_index_calls: list = []
    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=_reference_scope_runner_recording_generate_index(
            tmp_path, "RUN-GENIDX-CURRENT", scoped, generate_index_calls,
        ),
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)
    assert result["state"] == "VALIDATING"
    assert generate_index_calls == []


def test_apply_run_skips_generate_grouped_index_for_manually_curated_index(
    tmp_path: Path,
):
    # Mirrors pdf/net's real, currently-live containment flag (last_mechanism:
    # manual-edit-skill, bb9644e69c) -- a future case like it must stay protected
    # from any automatic re-invocation, stale stamp or not.
    scoped = "content/reference.aspose.org/en/pdf/net/SomeClass.md"
    manifest = _write_scope_manifest_and_plan(tmp_path, [scoped], "RUN-GENIDX-PROTECTED")
    _write_index_provenance(
        tmp_path, "pdf", "net",
        index_generator_version=None, last_mechanism="manual-edit-skill",
    )

    generate_index_calls: list = []
    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=_reference_scope_runner_recording_generate_index(
            tmp_path, "RUN-GENIDX-PROTECTED", scoped, generate_index_calls,
        ),
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    result = refresh_run.apply_run(manifest)
    assert result["state"] == "VALIDATING"
    assert generate_index_calls == []


def test_apply_refuses_scoped_file_changed_after_planning(tmp_path: Path):
    page = tmp_path / "content/docs.aspose.org/en/pdf/net/page.md"
    page.parent.mkdir(parents=True)
    page.write_text("original\n", encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(
        json.dumps({"paths": ["content/docs.aspose.org/en/pdf/net/page.md"]}),
        encoding="utf-8",
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="remediation",
        scope_manifest="scope.json",
        run_id="RUN-OCC",
        session_id="session-1",
    )
    refresh_run.prepare_run(manifest)
    page.write_text("concurrent edit\n", encoding="utf-8")
    with pytest.raises(refresh_run.RefreshRunError, match="outside a validated"):
        refresh_run.apply_run(manifest)


def test_interrupted_apply_resumes_from_planned_checkpoint():
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-RESUME",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    refresh_run._block(manifest, RuntimeError("interrupted"))
    assert manifest["state"] == "BLOCKED"
    assert manifest["resume_state"] == "PLANNED"


def test_verify_runs_scoped_content_and_link_gates(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-VERIFY",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    manifest["scope"]["digest"] = "sha256:scope"
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["state"] == "READY_TO_COMMIT"
    assert manifest["validation"]["content_audit"] == "PASS"
    assert manifest["validation"]["link_validation"] == "PASS"


def test_verify_run_writes_page_impact_matrix_and_records_digest(tmp_path: Path):
    """Task 2 (S9.1, closes G7): verify_run() must build and persist the
    Page-Impact Matrix as part of a normal successful verification, and
    record its digest in manifest["output_digests"] -- the same pattern
    already used for the validation.json digest just above it in the code.
    Also proves the FRESH-001-style repo_root lockstep fix actually works:
    page_impact_matrix.py must write under tmp_path (this test's own isolated
    repo_root), never the real checkout -- an earlier version of this wiring
    silently wrote into the real repo's reports/ tree instead."""
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-VERIFY-PIM", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["state"] == "READY_TO_COMMIT"
    assert manifest["output_digests"]["page_impact_matrix"] is not None
    assert manifest["output_digests"]["page_impact_matrix"].startswith("sha256:")
    matrix_path = tmp_path / "reports" / "refresh_review" / "pdf" / "net" / "page_impact_matrix.json"
    assert matrix_path.is_file()
    # Real repo's reports/ tree must never have been touched by this test --
    # this product has no real refresh_runs/pdf/net matrix on disk today.
    real_repo_root = Path(__file__).resolve().parents[3]
    real_matrix_path = real_repo_root / "reports" / "refresh_review" / "pdf" / "net" / "page_impact_matrix.json"
    assert not real_matrix_path.is_file()


def test_verify_run_writes_locale_staleness_summary(tmp_path: Path):
    """Task 11d (§9.8, closes G8/sizes F7): verify_run() must additionally size
    locale evidence-staleness as an advisory step (same placement/advisory
    pattern as the Page-Impact Matrix just above), recording a compact summary
    in manifest["locale_staleness_summary"] and writing the full report under
    reports/locale_staleness/{family}-{platform}.json -- both under this test's
    own isolated tmp_path repo_root, never the real checkout."""
    # The autouse _isolate fixture already creates knowledge/pdf/net/merged/model.yaml
    # with repo_sha=MODEL_SHA -- Knowledge.available also requires api_surface.json/
    # claims.json to exist alongside it, so add those (empty is sufficient).
    knowledge_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    (knowledge_dir / "api_surface.json").write_text("[]", encoding="utf-8")
    (knowledge_dir / "claims.json").write_text("[]", encoding="utf-8")
    stale_locale_page = tmp_path / "content/docs.aspose.org/fr/pdf/net/page.md"
    stale_locale_page.parent.mkdir(parents=True, exist_ok=True)
    stale_locale_page.write_text(
        "---\ntitle: Test\nevidence:\n  model_sha: old_sha\n---\n\nBody.\n", encoding="utf-8",
    )

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-VERIFY-LOCALE", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["state"] == "READY_TO_COMMIT"
    assert manifest.get("locale_staleness_error") is None
    summary = manifest["locale_staleness_summary"]
    assert summary["knowledge_repo_sha"] == MODEL_SHA
    assert summary["total_locale_files"] == 1
    assert summary["total_stale"] == 1
    report_path = tmp_path / "reports" / "locale_staleness" / "pdf-net.json"
    assert report_path.is_file()
    real_repo_root = Path(__file__).resolve().parents[3]
    real_report_path = real_repo_root / "reports" / "locale_staleness" / "pdf-net.json"
    assert not real_report_path.is_file()


def test_verify_run_locale_staleness_failure_is_advisory_only(tmp_path: Path):
    """The autouse fixture provides only model.yaml, not api_surface.json/claims.json
    -- Knowledge(...).available is False in this state (unlike the dedicated positive
    test above, which adds both). verify_run()'s own _model_state() check only reads
    model.yaml directly and is unaffected -- this failure is specific to the new
    locale-staleness step's own Knowledge(...) call, and must not block the run."""
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-VERIFY-LOCALE-ERR", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["state"] == "READY_TO_COMMIT"
    assert manifest["locale_staleness_summary"] is None
    assert manifest["locale_staleness_error"]
    # content_coverage_audit's own advisory step sits right after this one and
    # hits the identical missing-api_surface.json state -- but through
    # batch_reference.run()'s sys.exit(1), not a plain exception. Confirms
    # the (Exception, SystemExit) catch fix: a bare `except Exception` would
    # have let this propagate uncaught, crashing verify_run() entirely
    # instead of degrading gracefully (found live wiring this in).
    assert manifest["content_coverage_summary"] is None
    assert manifest["content_coverage_error"]
    assert "SystemExit" in manifest["content_coverage_error"]


def test_verify_run_writes_content_coverage_summary(tmp_path: Path):
    """Content-coverage audit (found live 2026-08-24, closes the "a real
    knowledge advance whose content generation was never triggered stays
    permanently invisible" gap): verify_run() must record a compact summary
    in manifest["content_coverage_summary"] and write the full report under
    reports/content_coverage/{family}-{platform}.json, mirroring the locale-
    staleness step immediately above it."""
    knowledge_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    # kind must be C#'s real tree-sitter node type ("class_declaration"), not
    # e.g. Python's "class_definition" -- _passes_platform_scope's kind
    # allowlist is platform-specific (found live: an earlier version of this
    # fixture used the wrong kind string and silently produced 0 candidates).
    (knowledge_dir / "api_surface.json").write_text(json.dumps([
        {"name": "HasPage", "kind": "class_declaration", "methods": [], "properties": [],
         "visibility": "public", "reachable": True, "file": "HasPage.cs"},
        {"name": "MissingPage", "kind": "class_declaration", "methods": [], "properties": [],
         "visibility": "public", "reachable": True, "file": "MissingPage.cs"},
    ]), encoding="utf-8")
    (knowledge_dir / "claims.json").write_text("[]", encoding="utf-8")
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "net"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "HasPage.md").write_text("---\nauto_updatable: true\n---\n# HasPage\n", encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-VERIFY-COVERAGE", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["state"] == "READY_TO_COMMIT"
    assert manifest.get("content_coverage_error") is None
    summary = manifest["content_coverage_summary"]
    assert summary["total_candidates"] == 2
    assert summary["missing_page_count"] == 1
    report_path = tmp_path / "reports" / "content_coverage" / "pdf-net.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["missing_classes"] == ["MissingPage"]
    real_repo_root = Path(__file__).resolve().parents[3]
    real_report_path = real_repo_root / "reports" / "content_coverage" / "pdf-net.json"
    assert not real_report_path.is_file()


def test_prepare_run_captures_content_coverage_before_snapshot(tmp_path: Path):
    """Completes G17's fix (deep-reassessment pass, 2026-08-24) per direct
    user instruction: the refresh-product skill must "keep note of what was
    there before" -- prepare_run() must capture a content-coverage baseline
    (manifest["content_coverage_before"]) before this run's own apply_run()
    writes anything, using the identical detector/mode verify_run()'s own
    "after" scan uses, so the two are directly comparable."""
    TestFullReferenceScopeResolution._write_api_surface_and_pages(tmp_path)
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-COVERAGE-BEFORE", session_id="session-1",
    )
    planning = tmp_path / "reports/refresh_runs/pdf/net/RUN-COVERAGE-BEFORE/planning/pdf/net"
    planning.mkdir(parents=True)
    (planning / "page_impact.json").write_text(json.dumps({"pages": []}), encoding="utf-8")

    prepared = refresh_run.prepare_run(manifest)

    assert prepared.get("content_coverage_before_error") is None
    before = prepared["content_coverage_before"]
    assert before["total_candidates"] == 2
    assert before["missing_page_count"] == 1
    assert before["missing_classes"] == ["MissingPage"]


def test_verify_run_computes_content_coverage_comparison_against_before_snapshot(
    tmp_path: Path,
):
    """Completes G17's fix: verify_run() must diff its own "after" scan
    against manifest["content_coverage_before"] (captured by prepare_run())
    to directly answer the user's ask -- "compare the newly generated pages
    to make sure everything existing as well new API references are there".
    newly_covered proves new/previously-missing references are now present;
    newly_missing flags the real regression case (had a page before this
    run, has none now); still_missing flags a pre-existing gap this run's
    generation did not close."""
    knowledge_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    (knowledge_dir / "api_surface.json").write_text(json.dumps([
        {"name": "Alpha", "kind": "class_declaration", "methods": [], "properties": [],
         "visibility": "public", "reachable": True, "file": "Alpha.cs"},
        {"name": "Beta", "kind": "class_declaration", "methods": [], "properties": [],
         "visibility": "public", "reachable": True, "file": "Beta.cs"},
        {"name": "Gamma", "kind": "class_declaration", "methods": [], "properties": [],
         "visibility": "public", "reachable": True, "file": "Gamma.cs"},
        {"name": "Delta", "kind": "class_declaration", "methods": [], "properties": [],
         "visibility": "public", "reachable": True, "file": "Delta.cs"},
    ]), encoding="utf-8")
    (knowledge_dir / "claims.json").write_text("[]", encoding="utf-8")
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "net"
    ref_dir.mkdir(parents=True, exist_ok=True)
    # Alpha and Beta have real pages on disk right now (Beta simulates a
    # page this run just generated); Gamma and Delta have none.
    (ref_dir / "Alpha.md").write_text("---\nauto_updatable: true\n---\n# Alpha\n", encoding="utf-8")
    (ref_dir / "Beta.md").write_text("---\nauto_updatable: true\n---\n# Beta\n", encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-COVERAGE-COMPARE", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    # Simulate prepare_run()'s own "before" snapshot directly: Beta and Delta
    # were missing before this run started; Alpha and Gamma were not.
    manifest["content_coverage_before"] = {
        "total_candidates": 4,
        "missing_page_count": 2,
        "missing_classes": ["Beta", "Delta"],
    }
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["state"] == "READY_TO_COMMIT"
    assert manifest.get("content_coverage_error") is None
    comparison = manifest["content_coverage_comparison"]
    # Beta: missing before, has a page now -- new API reference confirmed present.
    assert comparison["newly_covered"] == ["Beta"]
    # Gamma: NOT missing before (per the simulated baseline), has no page
    # now -- the real-regression signal: something that existed vanished.
    assert comparison["newly_missing"] == ["Gamma"]
    # Delta: missing before and still missing now -- a pre-existing gap,
    # not something this run broke.
    assert comparison["still_missing"] == ["Delta"]


def test_verify_run_content_coverage_comparison_is_none_without_before_snapshot(
    tmp_path: Path,
):
    """Negative control: a run whose manifest was never planned via
    prepare_run() (or ran in a mode/era before this fix) has no
    content_coverage_before at all -- verify_run() must degrade to
    content_coverage_comparison=None rather than raising."""
    knowledge_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    (knowledge_dir / "api_surface.json").write_text("[]", encoding="utf-8")
    (knowledge_dir / "claims.json").write_text("[]", encoding="utf-8")

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-COVERAGE-NOBASELINE", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["state"] == "READY_TO_COMMIT"
    assert manifest.get("content_coverage_before") is None
    assert manifest["content_coverage_comparison"] is None


def test_verify_records_truth_audit_as_advisory_not_blocking(tmp_path: Path):
    """MT030-2026-08-13: ADVISORY_VALIDATION_FIELDS must be recorded in the
    manifest but must NEVER block READY_TO_COMMIT, even on a truth_audit FAIL --
    truth-audit debt is systemic and pre-existing (TRUTH-AUDIT-DEBT-001); an
    immediate hard gate here would block nearly every future refresh repo-wide."""
    def _runner_with_failing_truth_audit(
        args: list[str], **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if any("truth_audit.py" in str(a) for a in args):
            return subprocess.CompletedProcess(args, 1, "", "FAIL: 3 findings")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=_runner_with_failing_truth_audit,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-VERIFY-TA", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    refresh_run.verify_run(manifest)

    assert manifest["validation"]["truth_audit"] == "FAIL"
    assert manifest["validation"]["content_audit"] == "PASS"
    # The advisory FAIL must not have blocked the state transition.
    assert manifest["state"] == "READY_TO_COMMIT"


def test_advisory_validation_fields_excluded_from_bind_commit_gate(tmp_path: Path):
    """The same advisory exclusion must hold at commit-binding time, not just
    verify_run() -- both not_pass checks read manifest['validation']. Reuses
    test_bind_commit_rejects_partial_run_commit's exact minimal setup (a
    deliberately incomplete diff-tree output that trips the UNRELATED "exactly
    match" evidence check) with truth_audit=FAIL added to validation: if the
    commit-ready gate wrongly included truth_audit, bind_commit would raise
    "Run validation is not commit-ready" instead -- proving the fix runs for
    real, not just that the two checks look alike on inspection."""
    commit_sha = "c" * 40

    def commit_runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\nRefresh-Run: RUN-COMMIT-TA\n"
                f"Refresh-Base: {HEAD_SHA}\nRefresh-Source-SHA: {MODEL_SHA}\n"
            )
        elif args[:2] == ["git", "diff-tree"]:
            output = "content/docs.aspose.org/en/pdf/net/one.md"  # partial -- trips a DIFFERENT check
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, output + "\n", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-COMMIT-TA", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/one.md",
        "content/docs.aspose.org/en/pdf/net/two.md",
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    manifest["validation"] = {field: "PASS" for field in refresh_run.VALIDATION_FIELDS}
    manifest["validation"]["truth_audit"] = "FAIL"  # the advisory field, deliberately failing
    refresh_run._transition(manifest, "READY_TO_COMMIT")
    _write_run_evidence(tmp_path, manifest, include_validation=True)

    with pytest.raises(refresh_run.RefreshRunError, match="exactly match"):
        refresh_run.bind_commit(
            "pdf", "net", "RUN-COMMIT-TA", commit_sha, session_id="session-1",
        )


def test_validation_attempts_are_immutable_and_manifest_referenced(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-VERIFY-TWICE",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    refresh_run._transition(manifest, "VALIDATING")

    refresh_run.verify_run(manifest)
    refresh_run.verify_run(manifest)

    saved = refresh_run._load_manifest("pdf", "net", "RUN-VERIFY-TWICE")
    assert saved["validation_attempt_refs"] == [
        "validation/attempt-01/result.json",
        "validation/attempt-02/result.json",
    ]
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-VERIFY-TWICE"
    assert all((run_root / ref).is_file() for ref in saved["validation_attempt_refs"])


def test_validation_exception_persists_immutable_unknown_attempt(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-VALIDATION-EXCEPTION",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    manifest["scope"]["digest"] = "sha256:scope"
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    refresh_run._transition(manifest, "VALIDATING")

    def raising_runner(args: list[str], **_: object):
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        raise RuntimeError(f"provider failed at {tmp_path}")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=raising_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
    )
    with pytest.raises(refresh_run.RefreshRunError, match="Validation did not pass"):
        refresh_run.verify_run(manifest)

    saved = refresh_run._load_manifest(
        "pdf", "net", "RUN-VALIDATION-EXCEPTION"
    )
    assert saved["validation_attempt_refs"] == [
        "validation/attempt-01/result.json"
    ]
    result_path = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-VALIDATION-EXCEPTION"
        / saved["validation_attempt_refs"][0]
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert set(payload["results"].values()) == {"UNKNOWN"}
    assert str(tmp_path) not in result_path.read_text(encoding="utf-8")


def test_stage_attempts_are_immutable_redacted_and_counted(tmp_path: Path):
    def stage_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        return subprocess.CompletedProcess(
            args,
            0,
            f"WARNING: used {tmp_path}\nSKIPPED one optional item\n",
            "",
        )

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=stage_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-STAGE-LOGS",
        session_id="session-1",
    )
    args = [str(tmp_path / "tool.py"), "API_KEY=top-secret"]
    refresh_run._require_command(args, "planning stage", manifest=manifest)
    refresh_run._require_command(args, "planning stage", manifest=manifest)

    stage_root = (
        tmp_path / "reports/refresh_runs/pdf/net/RUN-STAGE-LOGS/stages"
    )
    results = sorted(stage_root.glob("planning-stage-*.result.json"))
    assert [path.name for path in results] == [
        "planning-stage-01.result.json",
        "planning-stage-02.result.json",
    ]
    first = json.loads(results[0].read_text(encoding="utf-8"))
    second = json.loads(results[1].read_text(encoding="utf-8"))
    assert first["retry_count"] == 0
    assert second["retry_count"] == 1
    assert first["warnings"] == 1
    assert first["skips"] == 1
    serialized = results[0].read_text(encoding="utf-8")
    assert str(tmp_path) not in serialized
    assert "top-secret" not in serialized
    assert "<repo-root>" in serialized
    assert "<redacted>" in serialized
    saved = refresh_run._load_manifest("pdf", "net", "RUN-STAGE-LOGS")
    assert saved["stage_attempt_refs"] == [
        "stages/planning-stage-01.result.json",
        "stages/planning-stage-02.result.json",
    ]
    assert all((stage_root.parent / ref).is_file() for ref in saved["stage_attempt_refs"])


def _append_advisory_decision(
    tmp_path: Path,
    manifest: dict,
    *,
    page_path: str,
    disposition: str,
    body_hash_before: str,
) -> None:
    """Append one out-of-scope decision + matching receipt to an existing
    evidence bundle, and update the manifest digests _write_run_evidence
    already computed so only the NEW row is under test."""
    run_root = (
        tmp_path
        / "reports/refresh_runs"
        / manifest["family"]
        / manifest["platform"]
        / manifest["run_id"]
    )
    receipt_path = run_root / "receipts" / "RCP-ADVISORY.yaml"
    receipt_path.write_text(
        yaml.safe_dump({
            "content_refresh_receipt": {
                "receipt_id": "RCP-ADVISORY",
                "run_id": manifest["run_id"],
                "page_path": page_path,
                "old_hash": body_hash_before,
                "new_hash": body_hash_before,
            }
        }, sort_keys=False),
        encoding="utf-8",
    )
    row = {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "page_path": page_path,
        "surface": "reference",
        "locale": "en",
        "intended_action": "REFERENCE_GENERATE",
        "disposition": disposition,
        "body_hash_before": body_hash_before,
        "body_hash_after": body_hash_before,
        "frontmatter_hash_before": body_hash_before,
        "frontmatter_hash_after": body_hash_before,
        "receipt_ref": receipt_path.relative_to(run_root).as_posix(),
        "receipt_digest": refresh_run._file_digest(receipt_path),
        "evidence_claims_checked": [],
        "evidence_apis_checked": [],
        "validator_results": {"receipt": "PASS", "forbidden_claims": "PASS", "regrounding": "PASS"},
    }
    decisions_path = run_root / "page_decisions.jsonl"
    with open(decisions_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    receipts = sorted((run_root / "receipts").glob("*.yaml"))
    manifest["receipt_refs"] = [
        path.relative_to(tmp_path).as_posix() for path in receipts
    ]
    manifest["output_digests"]["page_decisions"] = refresh_run._file_digest(
        decisions_path
    )
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        "\n".join(
            f"{p.name}:{refresh_run._file_digest(p)}" for p in receipts
        ).encode("utf-8")
    ).hexdigest()
    refresh_run._save_manifest(manifest)


def test_casefold_path_diff_treats_case_only_variance_as_a_match():
    """Case-only path pairs (Windows/macOS filesystem aliasing, e.g. a
    generator writing 'Camera.md' where git still tracks 'camera.md') must
    not surface as a real diff on either side."""
    a_only, b_only = refresh_run._casefold_path_diff(
        {"content/reference.aspose.org/en/3d/java/camera.md", "content/x/Real.md"},
        {"content/reference.aspose.org/en/3d/java/Camera.md", "content/y/Other.md"},
    )
    assert a_only == {"content/x/Real.md"}
    assert b_only == {"content/y/Other.md"}


def test_casefold_path_diff_collapses_case_insensitive_duplicate():
    """A genuine duplicate that differs only in case on both sides is a
    match, not a diff entry from either set."""
    a_only, b_only = refresh_run._casefold_path_diff(
        {"content/a.md"}, {"content/A.md"}
    )
    assert a_only == set()
    assert b_only == set()


def test_assert_scope_ownership_tolerates_case_only_receipt_path(tmp_path: Path):
    """Regression test for the 2026-08-14 3d/java scoped-run finding: the OCC
    guard's allowed-hash lookup must merge case-insensitively too, or a
    receipt recorded under the generator's canonical casing ('Camera.md')
    fails to authorize the identical physical file the scope pinned under
    git's tracked casing ('camera.md')."""
    page_path = "content/reference.aspose.org/en/pdf/net/camera.md"
    page = tmp_path / page_path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\ntitle: Camera\n---\n\nBody.\n", encoding="utf-8")
    file_hash = refresh_run._path_hash(page_path)

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-CASEFOLD-OCC", session_id="s1"
    )
    manifest["scope"]["paths"] = [page_path]
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-CASEFOLD-OCC"
    scope_path = run_root / "scope.json"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": manifest["run_id"],
                "family": "pdf",
                "platform": "net",
                "paths": [page_path],
                "initial_hashes": {page_path: file_hash},
            }
        ),
        encoding="utf-8",
    )
    manifest["scope"]["digest"] = refresh_run._scope_digest(
        [page_path], manifest["scope"].get("input_digest")
    )
    manifest["output_digests"]["scope"] = refresh_run._file_digest(scope_path)

    # Receipt recorded under the generator's canonical class-name casing,
    # differing from the scope manifest's git-tracked casing above.
    receipt_page_path = "content/reference.aspose.org/en/pdf/net/Camera.md"
    receipt_path = run_root / "receipts" / "RCP-001.yaml"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        yaml.safe_dump(
            {
                "content_refresh_receipt": {
                    "receipt_id": "RCP-001",
                    "run_id": manifest["run_id"],
                    "page_path": receipt_page_path,
                    "old_hash": file_hash,
                    "new_hash": file_hash,
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    decisions_path = run_root / "page_decisions.jsonl"
    decisions_path.write_text(
        json.dumps(
            {
                "run_id": manifest["run_id"],
                "page_path": receipt_page_path,
                "receipt_ref": "receipts/RCP-001.yaml",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    refresh_run._save_manifest(manifest)

    refresh_run._assert_scope_ownership(manifest)  # must not raise


def test_augment_initial_hashes_treats_authorized_write_as_unchanged(
    tmp_path: Path,
):
    """Regression test for the 2026-08-14 3d/java scoped-run finding:
    _assert_run_evidence_ready's reconciliation call must not report a
    deliberately receipt-less page (TC-DUPIDX-02's _index.md regeneration)
    as 'missing' once its resulting hash has been recorded as authorized --
    but any OTHER, unauthorized drift on that same page must still block."""
    page_path = "content/reference.aspose.org/en/pdf/net/_index.md"
    page = tmp_path / page_path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("Original.\n", encoding="utf-8")
    initial_hash = refresh_run._path_hash(page_path)
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-AUGMENT"

    # No write yet: augmentation is a no-op (nothing recorded).
    assert refresh_run._augment_initial_hashes_with_extra_allowed(
        {page_path: initial_hash}, run_root
    ) == {page_path: initial_hash}

    # Authorized write: current hash becomes the accepted baseline.
    page.write_text("Regenerated by TC-DUPIDX-02.\n", encoding="utf-8")
    authorized_hash = refresh_run._path_hash(page_path)
    refresh_run._record_extra_allowed_hash(run_root, page_path, authorized_hash)
    augmented = refresh_run._augment_initial_hashes_with_extra_allowed(
        {page_path: initial_hash}, run_root
    )
    assert augmented[page_path] == authorized_hash

    # Further, unauthorized drift on top of the authorized write must still
    # surface as a real diff -- the fix narrows the gap, it doesn't remove
    # the safety property. Current bytes match neither the recorded
    # authorized hash nor the original initial_hash, so no override applies
    # and the caller's real_missing check still sees a mismatch.
    page.write_text("Unauthorized further edit.\n", encoding="utf-8")
    still_augmented = refresh_run._augment_initial_hashes_with_extra_allowed(
        {page_path: initial_hash}, run_root
    )
    assert still_augmented[page_path] == initial_hash
    assert refresh_run._path_hash(page_path) != still_augmented[page_path]


def test_assert_scope_ownership_honors_recorded_extra_allowed_hash(tmp_path: Path):
    """Regression test for the 2026-08-14 3d/java scoped-run finding: the
    TC-DUPIDX-02 grouped-index regeneration deliberately writes _index.md
    with no page_decisions.jsonl row of its own (see that call site's
    comment) -- _record_extra_allowed_hash() must authorize the resulting
    hash so this OCC guard does not block on the write it was told to make."""
    page_path = "content/reference.aspose.org/en/pdf/net/_index.md"
    page = tmp_path / page_path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\ntitle: Index\n---\n\nOriginal.\n", encoding="utf-8")
    initial_hash = refresh_run._path_hash(page_path)

    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-EXTRA-HASH", session_id="s1"
    )
    manifest["scope"]["paths"] = [page_path]
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-EXTRA-HASH"
    scope_path = run_root / "scope.json"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": manifest["run_id"],
                "family": "pdf",
                "platform": "net",
                "paths": [page_path],
                "initial_hashes": {page_path: initial_hash},
            }
        ),
        encoding="utf-8",
    )
    manifest["scope"]["digest"] = refresh_run._scope_digest(
        [page_path], manifest["scope"].get("input_digest")
    )
    manifest["output_digests"]["scope"] = refresh_run._file_digest(scope_path)
    refresh_run._save_manifest(manifest)

    # Simulate the generate-index writer: rewrites the file with no receipt
    # or decision row, exactly like apply_run()'s TC-DUPIDX-02 call site.
    page.write_text("---\ntitle: Index\n---\n\nRegenerated.\n", encoding="utf-8")
    new_hash = refresh_run._path_hash(page_path)
    assert new_hash != initial_hash

    with pytest.raises(refresh_run.RefreshRunError, match="changed outside"):
        refresh_run._assert_scope_ownership(manifest)

    refresh_run._record_extra_allowed_hash(run_root, page_path, new_hash)
    refresh_run._assert_scope_ownership(manifest)  # must not raise


def test_reconcile_scope_and_decisions_tolerates_case_only_page_path(
    tmp_path: Path,
):
    """Regression test for the 2026-08-14 3d/java scoped-run finding: a scope
    manifest built from git's tracked casing ('camera.md') and a decision row
    written with the generator's canonical class-name casing ('Camera.md')
    describe the same physical page on a case-insensitive filesystem and must
    not be reported as both missing and unexpected."""
    scope_paths = ["content/reference.aspose.org/en/3d/java/camera.md"]
    decision_rows = [
        {
            "page_path": "content/reference.aspose.org/en/3d/java/Camera.md",
            "disposition": "EVIDENCE_ONLY",
        }
    ]
    real_missing, real_unexpected = refresh_run._reconcile_scope_and_decisions(
        scope_paths, decision_rows, initial_hashes={}
    )
    assert real_missing == []
    assert real_unexpected == []


def test_evidence_ready_tolerates_out_of_scope_additive_generated_row(
    tmp_path: Path,
):
    """Integration test for _assert_run_evidence_ready using the shared
    _reconcile_scope_and_decisions() helper: an out-of-scope GENERATED row
    for a provably-new page must not block commit-readiness."""
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-EVIDENCE-OK", session_id="session-1"
    )
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    _append_advisory_decision(
        tmp_path,
        manifest,
        page_path="content/reference.aspose.org/en/pdf/net/NewClass.md",
        disposition="GENERATED",
        body_hash_before=_normalized_body_hash(""),
    )
    refresh_run._assert_run_evidence_ready(manifest)  # must not raise


def test_evidence_ready_blocks_out_of_scope_overwrite(tmp_path: Path):
    """Negative control: an out-of-scope GENERATED row whose body_hash_before
    proves real pre-existing content must still block."""
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-EVIDENCE-BAD", session_id="session-1"
    )
    manifest["scope"]["paths"] = ["content/docs.aspose.org/en/pdf/net/page.md"]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    _append_advisory_decision(
        tmp_path,
        manifest,
        page_path="content/reference.aspose.org/en/pdf/net/Existing.md",
        disposition="GENERATED",
        body_hash_before="sha256:" + "1" * 64,
    )
    with pytest.raises(refresh_run.RefreshRunError, match="exactly one decision"):
        refresh_run._assert_run_evidence_ready(manifest)


def test_stage_log_tampering_and_unbound_results_block_readiness(
    tmp_path: Path,
):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-STAGE-INTEGRITY",
        session_id="session-1",
    )
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    refresh_run._require_command(
        ["tool", "run"], "writer", manifest=manifest
    )
    run_root = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-STAGE-INTEGRITY"
    )
    log_path = run_root / "stages/writer-01.stdout.log"
    log_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(refresh_run.RefreshRunError, match="digest mismatch"):
        refresh_run._assert_run_evidence_ready(manifest)

    result_path = run_root / "stages/writer-01.result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    log_path.write_text("", encoding="utf-8")
    payload["stdout_digest"] = refresh_run._file_digest(log_path)
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest["stage_attempt_digests"][
        "stages/writer-01.result.json"
    ] = refresh_run._file_digest(result_path)
    orphan = run_root / "stages/orphan-01.result.json"
    orphan.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(refresh_run.RefreshRunError, match="unbound"):
        refresh_run._assert_run_evidence_ready(manifest)


def test_numeric_zero_result_labels_do_not_create_false_counts():
    assert refresh_run._result_counters(
        "WARNING: 0\nFAIL: 0\nSKIP: 0\n", ""
    ) == {"warnings": 0, "errors": 0, "skips": 0}
    assert refresh_run._result_counters(
        "Errors: 0 (failed to generate)\n", ""
    )["errors"] == 0


def test_partial_stage_artifact_advances_attempt_number(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-PARTIAL-STAGE",
        session_id="session-1",
    )
    stage_root = (
        tmp_path / "reports/refresh_runs/pdf/net/RUN-PARTIAL-STAGE/stages"
    )
    stage_root.mkdir()
    (stage_root / "planning-stage-01.stdout.log").write_text(
        "interrupted", encoding="utf-8"
    )

    refresh_run._require_command(
        ["tool", "arg"], "planning stage", manifest=manifest
    )

    assert (stage_root / "planning-stage-02.result.json").is_file()


def test_stage_exception_and_block_reason_are_redacted(tmp_path: Path):
    secret = "do-not-persist"

    def exception_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        raise RuntimeError(f"TOKEN={secret} at {tmp_path}")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=exception_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-STAGE-ERROR",
        session_id="session-1",
    )
    with pytest.raises(refresh_run.RefreshRunError) as raised:
        refresh_run._require_command(
            ["tool", f"PASSWORD={secret}"],
            "planning stage",
            manifest=manifest,
        )
    refresh_run._block(manifest, raised.value)

    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-STAGE-ERROR"
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run_root.rglob("*")
        if path.is_file()
    )
    assert secret not in serialized
    assert str(tmp_path) not in serialized
    assert "<redacted>" in serialized
    saved = refresh_run._load_manifest("pdf", "net", "RUN-STAGE-ERROR")
    assert saved["stage_attempt_refs"] == [
        "stages/planning-stage-01.result.json"
    ]


def test_page_decision_unknown_blocks_before_validator_commands(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-PAGE-UNKNOWN",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest, validator_value="UNKNOWN")
    refresh_run._transition(manifest, "VALIDATING")

    with pytest.raises(refresh_run.RefreshRunError, match="not commit-ready"):
        refresh_run.verify_run(manifest)
    assert not (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-PAGE-UNKNOWN/validation"
    ).exists()


def test_receipt_tamper_blocks_verification(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-RECEIPT-TAMPER",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    refresh_run._transition(manifest, "VALIDATING")
    receipt = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-RECEIPT-TAMPER/receipts/RCP-001.yaml"
    )
    receipt.write_text(receipt.read_text(encoding="utf-8") + "# tampered\n")

    with pytest.raises(refresh_run.RefreshRunError, match="evidence digest"):
        refresh_run.verify_run(manifest)


def test_unbound_receipt_blocks_even_when_aggregate_digest_is_updated(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-UNBOUND-RECEIPT",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    refresh_run._transition(manifest, "VALIDATING")
    receipts_root = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-UNBOUND-RECEIPT/receipts"
    )
    (receipts_root / "RCP-UNBOUND.yaml").write_text(
        "content_refresh_receipt:\n  receipt_id: RCP-UNBOUND\n",
        encoding="utf-8",
    )
    receipts = sorted(receipts_root.glob("*.yaml"))
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        "\n".join(
            f"{path.name}:{refresh_run._file_digest(path)}" for path in receipts
        ).encode("utf-8")
    ).hexdigest()
    refresh_run._save_manifest(manifest)

    with pytest.raises(refresh_run.RefreshRunError, match="unbound"):
        refresh_run.verify_run(manifest)


def test_scope_file_identity_mismatch_blocks_after_digest_rewrite(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-SCOPE-IDENTITY",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    refresh_run._transition(manifest, "VALIDATING")
    scope_path = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-SCOPE-IDENTITY/scope.json"
    )
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope["family"] = "words"
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    manifest["output_digests"]["scope"] = refresh_run._file_digest(scope_path)
    refresh_run._save_manifest(manifest)

    with pytest.raises(refresh_run.RefreshRunError, match="do not reconcile"):
        refresh_run.verify_run(manifest)


def test_seo_stability_is_independent_of_aggregate_verifier(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-SEO-INDEPENDENT",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    def verifier_fails_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if any(str(value).endswith("post_refresh_verify.py") for value in args):
            return subprocess.CompletedProcess(args, 1, "Check 9: FAIL\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=verifier_fails_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    with pytest.raises(refresh_run.RefreshRunError, match="Validation did not pass"):
        refresh_run.verify_run(manifest)
    assert manifest["validation"]["post_refresh_verify"] == "FAIL"
    assert manifest["validation"]["seo_stability"] == "PASS"
    detail = json.loads(
        (
            tmp_path
            / "reports/refresh_runs/pdf/net/RUN-SEO-INDEPENDENT/validation.json"
        ).read_text(encoding="utf-8")
    )
    assert detail["details"]["seo_stability"].get("derived_from") is None
    # seo_stability now runs through scoped_commands' chunking loop (found
    # live 2026-08-24, Task 14: G17's full-reference-scope fix can pin
    # 1000+ paths into scope, overflowing Windows' argv-length ceiling for
    # an inline *scope_paths invocation) -- its own command is split across
    # "command_prefix" (constant per chunk) and "chunks" (per-chunk detail),
    # not a single flat "command" list.
    assert any(
        value.endswith("seo_stability_check.py")
        for value in detail["details"]["seo_stability"]["command_prefix"]
    )


def test_verify_run_chunks_every_scoped_validator_for_a_large_scope(tmp_path: Path):
    """Found live 2026-08-24 (mission-plan-the-end-to-end-vast-hejlsberg.md
    Task 14, the real upstream E2E proof run): the G17 full-reference-scope
    fix routinely pins 1000+ paths into scope for upstream/combined mode.
    triage_confirm and seo_stability used to embed *scope_paths directly in
    their own single-invocation command list -- fine for a small PIA-scored
    prose scope, but a real crash (FileNotFoundError: [WinError 206] the
    filename or extension is too long -- Windows CreateProcess's real
    command-line-length ceiling, not a git/tool error) the moment scope
    exceeds a few hundred paths. Both were moved into scoped_commands'
    existing 40-per-chunk mechanism (already used by content_audit/
    link_validation). This is the load-bearing regression test: a scope
    of 85 paths must produce 3 chunks (40+40+5) for every scoped validator,
    never one call carrying all 85 paths at once."""
    scope_paths = [
        f"content/reference.aspose.org/en/pdf/net/Class{i:03d}.md" for i in range(85)
    ]
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-CHUNK-LARGE-SCOPE", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = scope_paths
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    scoped_scripts = (
        "audit.py", "link_validator.py", "triage_confirm.py", "seo_stability_check.py",
    )
    max_paths_per_call: dict[str, int] = {}

    def capturing_runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        str_args = [str(a) for a in args]
        for script in scoped_scripts:
            if any(a.endswith(script) for a in str_args):
                path_count = sum(1 for a in str_args if a in scope_paths)
                max_paths_per_call[script] = max(max_paths_per_call.get(script, 0), path_count)
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=capturing_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    refresh_run.verify_run(manifest)

    assert set(max_paths_per_call) == set(scoped_scripts)
    for script, max_count in max_paths_per_call.items():
        assert max_count <= 40, f"{script} received {max_count} paths in one call, expected <=40"
    # Confirm the full scope really was covered across chunks, not silently
    # truncated to the first chunk only.
    detail = json.loads(
        (
            tmp_path
            / "reports/refresh_runs/pdf/net/RUN-CHUNK-LARGE-SCOPE/validation.json"
        ).read_text(encoding="utf-8")
    )
    assert len(detail["details"]["seo_stability"]["chunks"]) == 3
    assert sum(c["page_count"] for c in detail["details"]["seo_stability"]["chunks"]) == 85
    assert len(detail["details"]["triage_confirm"]["chunks"]) == 3
    assert sum(c["page_count"] for c in detail["details"]["triage_confirm"]["chunks"]) == 85


def test_head_scope_conflicts_never_embeds_scope_paths_as_argv(tmp_path: Path):
    """Companion regression test for the same G17-scale finding: apply_run's
    (and verify_run's) own _head_scope_conflicts() used to call
    `git diff --name-only <prior>..<current> -- <every scope path>` --
    the exact same Windows argv-length crash for a 1000+-path scope. Fixed
    to compute the commit-to-commit diff unscoped and filter in Python.
    This test moves HEAD (so the check actually runs its git-diff branch,
    not the current==prior fast path) and asserts the git diff call never
    receives any scope path as an argv token, for a scope far larger than
    the old code could have handled."""
    scope_paths = [
        f"content/reference.aspose.org/en/pdf/net/Class{i:03d}.md" for i in range(600)
    ]
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-HEADCONFLICT-LARGE", session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = scope_paths
    refresh_run._transition(manifest, "PLANNED")

    diff_call_argv_lengths: list[int] = []
    moved_head = "c" * 40

    def moved_head_runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, moved_head + "\n", "")
        if args[:3] == ["git", "diff", "--name-only"]:
            diff_call_argv_lengths.append(len(args))
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=moved_head_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    conflicts = refresh_run._head_scope_conflicts(manifest)

    assert diff_call_argv_lengths, "expected the git diff --name-only branch to actually run"
    # ["git", "diff", "--name-only", "<prior>..<current>"] -- exactly 4 argv
    # tokens regardless of scope size, never scope_paths appended.
    assert diff_call_argv_lengths == [4]
    assert conflicts == []


def test_oracle_command_scoped_to_run_receipts(tmp_path: Path):
    """3d/net fan-out defect (successor to MT033's 6 chain fixes): the oracle
    stage was invoked with no --receipts flag, so refresh_oracle.py silently
    fell back to the platform's default reports/refresh_review/{f}/{p}/receipts/
    directory -- which can hold stale BODY_UPDATED receipts from an unrelated,
    much older process -- instead of this run's own scoped receipts. Live
    impact: 36 pre-existing-drift locale files got validated and FAILed
    oracle for a run that never touched them. The fix passes --receipts
    pointing at this run's own run_root/receipts directory explicitly."""
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-ORACLE-SCOPE",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    captured_oracle_args: list[list[str]] = []

    def capturing_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if any(str(value).endswith("refresh_oracle.py") for value in args):
            captured_oracle_args.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=capturing_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    refresh_run.verify_run(manifest)

    assert len(captured_oracle_args) == 1
    oracle_args = captured_oracle_args[0]
    assert "--receipts" in oracle_args
    receipts_arg = oracle_args[oracle_args.index("--receipts") + 1]
    expected_root = str(
        tmp_path / "reports/refresh_runs/pdf/net/RUN-ORACLE-SCOPE/receipts"
    )
    assert receipts_arg == expected_root


def test_independent_seo_failure_blocks_when_other_validators_pass(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-SEO-FAIL",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    def seo_fails_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if any(str(value).endswith("seo_stability_check.py") for value in args):
            return subprocess.CompletedProcess(args, 1, "SEO STABILITY: 1\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=seo_fails_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    with pytest.raises(refresh_run.RefreshRunError, match="seo_stability"):
        refresh_run.verify_run(manifest)
    assert manifest["validation"]["post_refresh_verify"] == "PASS"
    assert manifest["validation"]["seo_stability"] == "FAIL"


def test_cli_verify_failure_records_blocked_state(tmp_path: Path):
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-VERIFY-FAIL",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/page.md"
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    _write_run_evidence(tmp_path, manifest)

    def failing_audit_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if any(str(value).endswith("audit.py") for value in args):
            return subprocess.CompletedProcess(args, 1, "", "audit failed")
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=failing_audit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    assert refresh_run.main(
        [
            "verify",
            "--run-id",
            "RUN-VERIFY-FAIL",
            "--session-id",
            "session-1",
        ]
    ) == 2
    blocked = refresh_run._load_manifest(
        "pdf", "net", "RUN-VERIFY-FAIL"
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["resume_state"] == "VALIDATING"
    assert "content_audit" in blocked["failure_reason"]


def test_recover_restores_only_receipt_owned_output_and_abandons(tmp_path: Path):
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"
    base_content = "---\ntitle: Base\n---\n\nOriginal body.\n"
    output_content = "---\ntitle: Base\n---\n\nRun output.\n"
    base_payload = base_content.encode("utf-8")

    def recovery_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:3] == ["git", "cat-file", "--filters"]:
            return subprocess.CompletedProcess(
                args, 0, base_payload, b""
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=recovery_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    page = tmp_path / page_path
    page.parent.mkdir(parents=True)
    page.write_text(base_content, encoding="utf-8")
    base_payload = page.read_bytes()
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-RECOVER",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    manifest["scope"]["digest"] = "sha256:scope"
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    _replace_synthetic_output(
        tmp_path,
        manifest,
        page_path=page_path,
        content=output_content,
    )
    refresh_run._transition(manifest, "VALIDATING")

    recovered = refresh_run.recover_run(
        "pdf",
        "net",
        "RUN-RECOVER",
        reason="Rejected page-level UNKNOWN",
        session_id="session-1",
    )

    assert recovered["state"] == "ABANDONED"
    assert page.read_bytes() == base_payload
    assert recovered["recovery"]["restored_paths"] == [page_path]
    assert not (
        tmp_path / "reports/refresh_runs/pdf/net/ACTIVE.json"
    ).exists()


def test_recover_refuses_scoped_path_changed_after_run_output(tmp_path: Path):
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"
    base_content = "---\ntitle: Base\n---\n\nOriginal body.\n"
    output_content = "---\ntitle: Base\n---\n\nRun output.\n"

    def recovery_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess:
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:3] == ["git", "cat-file", "--filters"]:
            return subprocess.CompletedProcess(
                args, 0, base_content.encode("utf-8"), b""
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=recovery_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    page = tmp_path / page_path
    page.parent.mkdir(parents=True)
    page.write_text(base_content, encoding="utf-8")
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-RECOVER-CONFLICT",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    manifest["scope"]["digest"] = "sha256:scope"
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest)
    _replace_synthetic_output(
        tmp_path,
        manifest,
        page_path=page_path,
        content=output_content,
    )
    refresh_run._transition(manifest, "VALIDATING")
    page.write_text("concurrent edit\n", encoding="utf-8")

    with pytest.raises(refresh_run.RefreshRunError, match="Recovery refused"):
        refresh_run.recover_run(
            "pdf",
            "net",
            "RUN-RECOVER-CONFLICT",
            reason="test",
            session_id="session-1",
        )
    assert page.read_text(encoding="utf-8") == "concurrent edit\n"
    assert manifest["state"] == "VALIDATING"


def test_bind_commit_rejects_partial_run_commit(tmp_path: Path):
    commit_sha = "c" * 40

    def commit_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\n"
                "Refresh-Run: RUN-COMMIT\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
        elif args[:2] == ["git", "diff-tree"]:
            output = "content/docs.aspose.org/en/pdf/net/one.md"
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, output + "\n", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-COMMIT",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [
        "content/docs.aspose.org/en/pdf/net/one.md",
        "content/docs.aspose.org/en/pdf/net/two.md",
    ]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["receipt_refs"] = ["receipts/RCP-001.yaml"]
    manifest["page_decision_ref"] = "page_decisions.jsonl"
    refresh_run._transition(manifest, "VALIDATING")
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    refresh_run._transition(manifest, "READY_TO_COMMIT")
    _write_run_evidence(tmp_path, manifest, include_validation=True)

    with pytest.raises(refresh_run.RefreshRunError, match="exactly match"):
        refresh_run.bind_commit(
            "pdf",
            "net",
            "RUN-COMMIT",
            commit_sha,
            session_id="session-1",
        )


def test_bind_commit_rejects_changed_not_affected_page(tmp_path: Path):
    commit_sha = "c" * 40
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"

    def commit_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\n"
                "Refresh-Run: RUN-NOT-AFFECTED\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
        elif args[:2] == ["git", "diff-tree"]:
            output = page_path
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, output + "\n", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-NOT-AFFECTED",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    _write_run_evidence(
        tmp_path,
        manifest,
        dispositions={page_path: "NOT_AFFECTED"},
        include_validation=True,
    )
    refresh_run._transition(manifest, "VALIDATING")
    refresh_run._transition(manifest, "READY_TO_COMMIT")

    with pytest.raises(refresh_run.RefreshRunError, match="exactly match"):
        refresh_run.bind_commit(
            "pdf",
            "net",
            "RUN-NOT-AFFECTED",
            commit_sha,
            session_id="session-1",
        )


def test_bind_commit_tolerates_extra_allowed_hash_for_a_genuinely_unchanged_page(
    tmp_path: Path,
):
    """Found live 2026-08-28, cells/typescript: apply_run()'s own final
    normalization pass re-registers EVERY already-registered extra_allowed
    path with its current hash "whether or not actually rewritten -- a no-op
    result for an unchanged page is harmless" (see that pass's own comment).
    A page that backlink-reconciliation (or any other stage) scanned and
    registered but genuinely left untouched must not be rejected as
    'missing' from the commit's real diff just because it sits in the
    extra_allowed_hashes sidecar -- that sidecar only proves the write was
    AUTHORIZED if it happened, not that it DID happen."""
    commit_sha = "c" * 40
    scoped_page = "content/docs.aspose.org/en/pdf/net/page.md"
    untouched_page = "content/docs.aspose.org/en/pdf/net/untouched.md"

    def commit_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\n"
                "Refresh-Run: RUN-EXTRA-NOOP\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
        elif args[:2] == ["git", "diff-tree"]:
            # Only the scoped page actually changed -- untouched_page is
            # deliberately absent, matching a genuinely no-op registration.
            output = scoped_page
        elif args[:3] == ["git", "cat-file", "--filters"]:
            # Matches _write_run_evidence's own default scoped-page content
            # exactly -- the wrapper below appends the trailing "\n" every
            # branch relies on, so this literal must NOT include one itself.
            return subprocess.CompletedProcess(
                args, 0, "---\ntitle: Test\n---\n\nGrounded body.\n", ""
            )
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, output + "\n", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-EXTRA-NOOP",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [scoped_page]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    _write_run_evidence(
        tmp_path,
        manifest,
        dispositions={scoped_page: "BODY_UPDATED"},
        include_validation=True,
    )
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-EXTRA-NOOP"
    # _write_run_evidence's own page.write_text() uses platform-default
    # newline translation (CRLF on Windows); rewrite with newline="" so the
    # on-disk bytes are bare-LF everywhere, matching both the receipt hash
    # and this test's cat-file literal consistently (mirrors
    # test_bind_commit_tolerates_out_of_scope_additive_generated_page).
    scoped_content = "---\ntitle: Test\n---\n\nGrounded body.\n"
    scoped_disk = tmp_path / scoped_page
    scoped_disk.write_text(scoped_content, encoding="utf-8", newline="")
    scoped_receipt_path = run_root / "receipts" / "RCP-001.yaml"
    scoped_doc = yaml.safe_load(scoped_receipt_path.read_text(encoding="utf-8"))
    scoped_hash = refresh_run._path_hash(scoped_page)
    scoped_doc["content_refresh_receipt"]["new_hash"] = scoped_hash
    scoped_receipt_path.write_text(
        yaml.safe_dump(scoped_doc, sort_keys=False), encoding="utf-8"
    )
    decisions_path = run_root / "page_decisions.jsonl"
    rows = [json.loads(l) for l in decisions_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for row in rows:
        if row["page_path"] == scoped_page:
            row["body_hash_after"] = _normalized_body_hash(scoped_content)
            row["frontmatter_hash_after"] = _frontmatter_hash(scoped_content)
            row["receipt_digest"] = refresh_run._file_digest(scoped_receipt_path)
    decisions_path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    receipts = sorted((run_root / "receipts").glob("*.yaml"))
    manifest["output_digests"]["page_decisions"] = refresh_run._file_digest(decisions_path)
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        "\n".join(f"{p.name}:{refresh_run._file_digest(p)}" for p in receipts).encode("utf-8")
    ).hexdigest()
    refresh_run._save_manifest(manifest)
    # Simulate apply_run()'s final normalization pass: untouched_page was
    # scanned (e.g. by backlink-reconciliation) and its CURRENT, unchanged
    # hash re-registered -- it was never actually rewritten and has no
    # decision row of its own.
    untouched_disk = tmp_path / untouched_page
    untouched_disk.parent.mkdir(parents=True, exist_ok=True)
    untouched_disk.write_text("---\ntitle: Untouched\n---\n\nBody.\n", encoding="utf-8", newline="")
    refresh_run._record_extra_allowed_hash(
        run_root, untouched_page, refresh_run._path_hash(untouched_page)
    )
    refresh_run._transition(manifest, "VALIDATING")
    refresh_run._transition(manifest, "READY_TO_COMMIT")

    result = refresh_run.bind_commit(
        "pdf",
        "net",
        "RUN-EXTRA-NOOP",
        commit_sha,
        session_id="session-1",
    )
    assert result["state"] == "COMMITTED"
    assert result["commit_sha"] == commit_sha


def test_bind_commit_rejects_substituted_in_scope_output(tmp_path: Path):
    commit_sha = "c" * 40
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"

    def commit_runner(
        args: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
        if args[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args, 0, commit_sha + "\n", "")
        if args[:3] == ["git", "show", "-s"]:
            message = (
                "refresh\n\n"
                "Refresh-Run: RUN-SUBSTITUTED\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
            return subprocess.CompletedProcess(args, 0, message, "")
        if args[:2] == ["git", "diff-tree"]:
            return subprocess.CompletedProcess(args, 0, page_path + "\n", "")
        if args[:2] == ["git", "show"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "---\ntitle: Substituted\n---\n\nDifferent body.\n",
                "",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
        now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-SUBSTITUTED",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["scope"]["paths"] = [page_path]
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    _write_run_evidence(tmp_path, manifest, include_validation=True)
    refresh_run._transition(manifest, "VALIDATING")
    refresh_run._transition(manifest, "READY_TO_COMMIT")

    with pytest.raises(refresh_run.RefreshRunError, match="does not match"):
        refresh_run.bind_commit(
            "pdf",
            "net",
            "RUN-SUBSTITUTED",
            commit_sha,
            session_id="session-1",
        )


def test_bind_commit_rejects_duplicate_refresh_trailer(tmp_path: Path):
    commit_sha = "c" * 40
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"

    def commit_runner(args: list[str], **_: object):
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\n"
                "Refresh-Run: RUN-DUP-TRAILER\n"
                "Refresh-Run: CONFLICT\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, output + "\n", "")

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-DUP-TRAILER",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["paths"] = [page_path]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest, include_validation=True)
    refresh_run._transition(manifest, "VALIDATING")
    refresh_run._transition(manifest, "READY_TO_COMMIT")

    with pytest.raises(refresh_run.RefreshRunError, match="duplicate"):
        refresh_run.bind_commit(
            "pdf",
            "net",
            "RUN-DUP-TRAILER",
            commit_sha,
            session_id="session-1",
        )


def test_commit_trailer_parser_ignores_matching_body_paragraph():
    message = (
        "refresh\n\n"
        "Refresh-Run: RUN-BODY-SPOOF\n"
        f"Refresh-Base: {HEAD_SHA}\n"
        f"Refresh-Source-SHA: {MODEL_SHA}\n\n"
        "These examples are explanatory body text, not commit trailers.\n"
    )

    assert refresh_run._commit_trailer_values(message) == {}


def test_commit_trailer_parser_accepts_only_final_trailer_block():
    message = (
        "refresh\n\n"
        "The body may mention Refresh-Run: WRONG inline.\n\n"
        "Refresh-Run: RUN-TRAILER\n"
        f"Refresh-Base: {HEAD_SHA}\n"
        f"Refresh-Source-SHA: {MODEL_SHA}\n"
        "Signed-off-by: Test Operator <operator@example.com>\n"
    )

    assert refresh_run._commit_trailer_values(message) == {
        "Refresh-Run": ["RUN-TRAILER"],
        "Refresh-Base": [HEAD_SHA],
        "Refresh-Source-SHA": [MODEL_SHA],
        "Signed-off-by": ["Test Operator <operator@example.com>"],
    }


def test_bind_commit_rejects_raw_byte_substitution_with_same_body_hash(
    tmp_path: Path,
):
    commit_sha = "c" * 40
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"

    def commit_runner(args: list[str], **kwargs: object):
        binary = kwargs.get("text") is False
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA + "\n"
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha + "\n"
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\n"
                "Refresh-Run: RUN-RAW-SUBSTITUTION\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
        elif args[:2] == ["git", "diff-tree"]:
            output = page_path + "\n"
        elif args[:3] == ["git", "cat-file", "--filters"]:
            output = "---\ntitle: Test\n---\n\nGrounded body.\n"
        else:
            output = ""
        rendered = output.encode("utf-8") if binary else output
        empty = b"" if binary else ""
        return subprocess.CompletedProcess(args, 0, rendered, empty)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-RAW-SUBSTITUTION",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["paths"] = [page_path]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest, include_validation=True)
    refresh_run._transition(manifest, "VALIDATING")
    refresh_run._transition(manifest, "READY_TO_COMMIT")

    with pytest.raises(refresh_run.RefreshRunError, match="does not match"):
        refresh_run.bind_commit(
            "pdf",
            "net",
            "RUN-RAW-SUBSTITUTION",
            commit_sha,
            session_id="session-1",
        )


def test_bind_commit_tolerates_preexisting_crlf_committed_content(
    tmp_path: Path,
):
    """Regression test for the 2026-08-14 3d/java scoped-run finding: a page
    that was already CRLF in git history (untouched, NOT_AFFECTED
    disposition) has a receipt.new_hash computed from the real CRLF bytes,
    but a body_hash_after/frontmatter_hash_after computed from a
    universal-newline (LF-normalized) read at write time. Verifying via a
    raw .decode() of `git cat-file --filters` output preserves the real
    CRLF and produces a false mismatch against those LF-based hashes."""
    import hashlib as _hashlib
    from commands.content.body_refresh import _frontmatter_hash, _normalized_body_hash

    commit_sha = "d" * 40
    page_path = "content/docs.aspose.org/en/pdf/net/page.md"
    lf_text = "---\ntitle: Test\n---\n\nGrounded body.\n"
    crlf_bytes = lf_text.replace("\n", "\r\n").encode("utf-8")
    raw_hash = "sha256:" + _hashlib.sha256(crlf_bytes).hexdigest()

    def commit_runner(args: list[str], **kwargs: object):
        binary = kwargs.get("text") is False
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA + "\n"
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha + "\n"
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\n"
                "Refresh-Run: RUN-PREEXISTING-CRLF\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
        elif args[:2] == ["git", "diff-tree"]:
            output = page_path + "\n"
        elif args[:3] == ["git", "cat-file", "--filters"]:
            if binary:
                return subprocess.CompletedProcess(args, 0, crlf_bytes, b"")
            output = crlf_bytes.decode("utf-8")
        else:
            output = ""
        rendered = output.encode("utf-8") if binary else output
        empty = b"" if binary else ""
        return subprocess.CompletedProcess(args, 0, rendered, empty)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
    )
    manifest = refresh_run.create_run(
        "pdf",
        "net",
        mode="upstream",
        run_id="RUN-PREEXISTING-CRLF",
        session_id="session-1",
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["paths"] = [page_path]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    # _write_run_evidence writes the page and derives its receipt/decision
    # hashes from that written (LF) content -- but the receipt's own
    # new_hash must match the CRLF bytes actually "committed" above, so
    # overwrite it post-hoc the same way the real writer would have (raw
    # hash of final bytes, LF-based body/frontmatter hashes).
    _write_run_evidence(tmp_path, manifest, include_validation=True)
    run_root = tmp_path / "reports/refresh_runs/pdf/net/RUN-PREEXISTING-CRLF"
    receipt_path = run_root / "receipts/RCP-001.yaml"
    receipt_doc = yaml.safe_load(receipt_path.read_text(encoding="utf-8"))
    receipt_doc["content_refresh_receipt"]["new_hash"] = raw_hash
    receipt_path.write_text(yaml.safe_dump(receipt_doc, sort_keys=False), encoding="utf-8")
    decisions_path = run_root / "page_decisions.jsonl"
    rows = [json.loads(l) for l in decisions_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for row in rows:
        row["body_hash_after"] = _normalized_body_hash(lf_text)
        row["frontmatter_hash_after"] = _frontmatter_hash(lf_text)
        row["receipt_digest"] = refresh_run._file_digest(receipt_path)
    decisions_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    manifest["output_digests"]["page_decisions"] = refresh_run._file_digest(decisions_path)
    manifest["output_digests"]["receipts"] = "sha256:" + _hashlib.sha256(
        f"{receipt_path.name}:{refresh_run._file_digest(receipt_path)}".encode("utf-8")
    ).hexdigest()
    refresh_run._save_manifest(manifest)
    refresh_run._transition(manifest, "VALIDATING")
    refresh_run._transition(manifest, "READY_TO_COMMIT")

    refresh_run.bind_commit(
        "pdf", "net", "RUN-PREEXISTING-CRLF", commit_sha, session_id="session-1",
    )  # must not raise


def test_bind_commit_tolerates_out_of_scope_additive_generated_page(
    tmp_path: Path,
):
    """A brand-new reference page batch_reference.py generates from
    api_surface.json (a GENERATED row whose page_path was never in scope.json
    -- new classes can't be named at PLANNED time since they don't exist yet)
    must not be rejected as 'outside the pinned run scope'. Mirrors the same
    tolerance _reconcile_scope_and_decisions already gives apply_run's own
    reconciliation, via the shared _allowed_commit_paths() helper."""
    commit_sha = "c" * 40
    scoped_page = "content/docs.aspose.org/en/pdf/net/page.md"
    new_page = "content/reference.aspose.org/en/pdf/net/NewClass.md"
    # Bare-LF literals matching what _write_run_evidence's own read_text()
    # round-trip produces (universal newlines) -- these are what body_refresh
    # would actually hash, not whatever bytes a platform-default write_text()
    # happens to put on disk. git cat-file --filters reflects the real
    # committed blob (already LF-normalized for this repo), so mocking with
    # these literals -- not a raw disk read -- is the faithful simulation.
    scoped_content = "---\ntitle: Test\n---\n\nGrounded body.\n"
    new_content = "---\ntitle: NewClass\n---\n\nGenerated content.\n"
    new_page_hash = "sha256:" + hashlib.sha256(
        new_content.encode("utf-8")
    ).hexdigest()

    def commit_runner(args: list[str], **kwargs: object):
        binary = kwargs.get("text") is False
        if args == ["git", "rev-parse", "HEAD"]:
            output = HEAD_SHA + "\n"
        elif args[:2] == ["git", "rev-parse"]:
            output = commit_sha + "\n"
        elif args[:3] == ["git", "show", "-s"]:
            output = (
                "refresh\n\n"
                "Refresh-Run: RUN-NEW-PAGE\n"
                f"Refresh-Base: {HEAD_SHA}\n"
                f"Refresh-Source-SHA: {MODEL_SHA}\n"
            )
        elif args[:2] == ["git", "diff-tree"]:
            output = scoped_page + "\n" + new_page + "\n"
        elif args[:3] == ["git", "cat-file", "--filters"]:
            output = (
                new_content if args[-1].endswith(new_page) else scoped_content
            )
        else:
            output = ""
        rendered = output.encode("utf-8") if binary else output
        empty = b"" if binary else ""
        return subprocess.CompletedProcess(args, 0, rendered, empty)

    refresh_run.configure(
        repo_root=tmp_path,
        command_runner=commit_runner,
        source_sha_resolver=lambda _f, _p: MODEL_SHA,
    )
    manifest = refresh_run.create_run(
        "pdf", "net", mode="upstream", run_id="RUN-NEW-PAGE", session_id="session-1"
    )
    manifest["target_model_sha"] = MODEL_SHA
    manifest["target_source_sha"] = MODEL_SHA
    manifest["scope"]["paths"] = [scoped_page]
    manifest["scope"]["digest"] = "sha256:scope"
    manifest["validation"] = {
        field: "PASS" for field in refresh_run.VALIDATION_FIELDS
    }
    refresh_run._transition(manifest, "PLANNED")
    refresh_run._transition(manifest, "APPLYING")
    _write_run_evidence(tmp_path, manifest, include_validation=True)
    # _write_run_evidence's own page.write_text() uses platform-default
    # newline translation (CRLF on Windows), while its body/frontmatter
    # hashes come from a read_text() round-trip (bare LF) -- rewrite with
    # newline="" so the on-disk bytes are bare-LF everywhere, matching both
    # the receipt hash and this test's cat-file literal consistently (a real
    # LF-normalized git checkout would look like this uniformly).
    scoped_page_disk = tmp_path / scoped_page
    scoped_page_disk.write_text(scoped_content, encoding="utf-8", newline="")
    scoped_receipt_path = (
        tmp_path / "reports/refresh_runs/pdf/net/RUN-NEW-PAGE/receipts/RCP-001.yaml"
    )
    scoped_doc = yaml.safe_load(scoped_receipt_path.read_text(encoding="utf-8"))
    scoped_hash = refresh_run._path_hash(scoped_page)
    scoped_doc["content_refresh_receipt"]["old_hash"] = scoped_hash
    scoped_doc["content_refresh_receipt"]["new_hash"] = scoped_hash
    scoped_receipt_path.write_text(
        yaml.safe_dump(scoped_doc, sort_keys=False), encoding="utf-8"
    )
    _append_advisory_decision(
        tmp_path,
        manifest,
        page_path=new_page,
        disposition="GENERATED",
        body_hash_before=_normalized_body_hash(""),
    )
    new_page_disk = tmp_path / new_page
    new_page_disk.parent.mkdir(parents=True, exist_ok=True)
    # newline="" disables platform-default translation so the on-disk bytes
    # are exactly new_content.encode("utf-8") -- matching new_page_hash and
    # the cat-file mock above bit-for-bit, the same way a real LF-normalized
    # git checkout would.
    new_page_disk.write_text(new_content, encoding="utf-8", newline="")
    # The advisory receipt/decision must match the real committed bytes for
    # bind_commit's raw-byte reconciliation, unlike the body-hash-only checks
    # _assert_run_evidence_ready performs.
    receipt_path = (
        tmp_path
        / "reports/refresh_runs/pdf/net/RUN-NEW-PAGE/receipts/RCP-ADVISORY.yaml"
    )
    doc = yaml.safe_load(receipt_path.read_text(encoding="utf-8"))
    doc["content_refresh_receipt"]["new_hash"] = new_page_hash
    receipt_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    decisions_path = tmp_path / "reports/refresh_runs/pdf/net/RUN-NEW-PAGE/page_decisions.jsonl"
    rows = [json.loads(l) for l in decisions_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for row in rows:
        if row["page_path"] == new_page:
            row["body_hash_after"] = _normalized_body_hash(new_content)
            row["frontmatter_hash_after"] = _frontmatter_hash(new_content)
            row["receipt_digest"] = refresh_run._file_digest(receipt_path)
        elif row["page_path"] == scoped_page:
            row["receipt_digest"] = refresh_run._file_digest(scoped_receipt_path)
    decisions_path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    receipts = sorted((tmp_path / "reports/refresh_runs/pdf/net/RUN-NEW-PAGE/receipts").glob("*.yaml"))
    manifest["output_digests"]["page_decisions"] = refresh_run._file_digest(decisions_path)
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        "\n".join(f"{p.name}:{refresh_run._file_digest(p)}" for p in receipts).encode("utf-8")
    ).hexdigest()
    refresh_run._save_manifest(manifest)
    refresh_run._transition(manifest, "VALIDATING")
    refresh_run._transition(manifest, "READY_TO_COMMIT")

    result = refresh_run.bind_commit(
        "pdf", "net", "RUN-NEW-PAGE", commit_sha, session_id="session-1",
    )
    assert result["state"] == "COMMITTED"
    assert result["commit_sha"] == commit_sha


def test_locate_run_rejects_unsafe_glob_identity():
    with pytest.raises(refresh_run.RefreshRunError, match="run_id"):
        refresh_run._locate_run("*")
