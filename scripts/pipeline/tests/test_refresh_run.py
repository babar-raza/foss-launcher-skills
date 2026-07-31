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


MODEL_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _runner(
    args: list[str],
    **_: object,
) -> subprocess.CompletedProcess[str]:
    if args[:3] == ["git", "rev-parse", "HEAD"]:
        return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
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
    assert any(
        value.endswith("seo_stability_check.py")
        for value in detail["details"]["seo_stability"]["command"]
    )


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


def test_locate_run_rejects_unsafe_glob_identity():
    with pytest.raises(refresh_run.RefreshRunError, match="run_id"):
        refresh_run._locate_run("*")
