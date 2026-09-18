"""install_defect_sweep.py — PKGINSTALL-DEFECT-SWEEP-REDESIGN (MT066 plan
section R.3.4), install_literal_sweep.py's successor.

TC-09's original sweep (install_literal_sweep.py, reused here unchanged --
run_literal_sweep() is a thin call-through to its run_sweep()) only ever
covered ONE defect class: literal (non-shortcode) install-command text. This
module extends the same recurring, read-only, portfolio-wide discipline to
install_recipe's two safety checks (_verify_publish_channel_claims,
_verify_no_unpublished_disclosure -- PKGINSTALL-INSTALL-RECIPE-POLICY-FIX/
ST-054 TC-14), which have never run on any schedule despite being real,
tested, and already the source of a confirmed, live, still-open defect
(PUBLISH-CLAIM-CONTRADICTION-001, 89 findings across 9 products,
backlog/BACKLOG.md).

Every row from both sweeps is appended into ReconciliationStore.append_batch()
under one shared sweep_run_id -- the durable link this mission's own root-
cause analysis found missing everywhere (governing plan section R.1 point 1:
"no state persists between detection and remediation").

TC-PKG-02-READINESS-GATE-FIX (2026-09-18): the rows built above are ALL
product-level aggregates at a synthetic path
(reports/audit/install-defect-sweep/{family}-{platform}), never a real
content/ path. Three independent taskcards in this same mission
(TC-PKG-02-05, TC-PKG-02-07, TC-PKG-02-18) confirmed live that
locale_patch.py's is_english_source_ready() -- which keys its readiness
lookup by the real repo-relative content file path -- can therefore NEVER
be satisfied by this writer for any real file; it had only ever been
satisfied by a hand-supplied workaround row. _english_source_file_rows()
closes that gap by additionally emitting one real per-file row for every
ENGLISH-SOURCE content file the literal sweep scans (locale == "en" --
the only path shape is_english_source_ready() ever looks up, since a
locale-propagation caller only ever asks about the source it is about to
propagate FROM, never an arbitrary locale copy). Scoped to English-source
files only, not the full ~21,000-file corpus: confirmed live 2026-09-18 that
only 918 of those files are English-source (versus 20,956 total), so this
keeps the reconciliation store's per-sweep growth two orders of magnitude
smaller than a full-corpus emission would, while still covering every path
is_english_source_ready() can ever be asked about.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.install_defect_sweep
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.install_defect_sweep --issues-out /tmp/issues.json
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from commands.ops import install_literal_sweep  # noqa: E402
from content_eval.loader import load_all_products  # noqa: E402
from content_eval.evaluators.install_recipe import InstallRecipeEvaluator  # noqa: E402
from reconciliation_store import ReconciliationStore  # noqa: E402
from audit.package_install_literal import verify_package_install_literals  # noqa: E402
from commands.content.package_install_migrator import _locale_from_path  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT

# The 2 install_recipe checks this sweep runs -- deliberately NOT
# _verify_install_accuracy (noisier, still experimental-only, out of this
# taskcard's scope per governing plan R.3.4/R.2's "explicitly rejected
# approaches": chasing every install_recipe finding, not just the 2
# already-tested safety checks).
_DEFECT_CLASS_PUBLISH_CLAIM = "publish_claim_contradiction"
_DEFECT_CLASS_UNPUBLISHED_DISCLOSURE = "unpublished_disclosure"
_DEFECT_CLASS_LITERAL = "literal_install_command"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    install_literal_sweep.configure(repo_root=REPO_ROOT)


def run_literal_sweep(*, registry: "dict[str, Any] | None" = None) -> dict[str, Any]:
    """Unchanged reuse of install_literal_sweep.run_sweep() -- see that
    module's own docstring for the literal-text defect class's detection
    method (verify_package_install_literals, unmodified)."""
    return install_literal_sweep.run_sweep(registry=registry)


def run_install_recipe_sweep(
    *, products: "dict[tuple[str, str], list] | None" = None,
) -> dict[str, Any]:
    """Run install_recipe's 2 safety checks portfolio-wide (English-source
    pages only -- content_eval.loader.load_all_products()'s own existing
    scope, matching the methodology that first found
    PUBLISH-CLAIM-CONTRADICTION-001; locale copies are a known, explicitly
    out-of-scope gap for a future pass, not silently expanded here).

    Calls the 2 check methods directly (not the evaluator's full evaluate()),
    deliberately excluding _verify_install_accuracy -- see module docstring.
    """
    evaluator = InstallRecipeEvaluator()
    all_products = products if products is not None else load_all_products()

    per_product: list[dict[str, Any]] = []
    total_pages_checked = 0
    total_publish_claim_findings = 0
    total_unpublished_disclosure_findings = 0

    for (family, platform), pages in sorted(all_products.items()):
        publish_claim_count = 0
        unpublished_disclosure_count = 0
        sample_publish_claim: list[dict[str, Any]] = []
        sample_unpublished_disclosure: list[dict[str, Any]] = []

        for page in pages:
            publish_claim_findings = evaluator._verify_publish_channel_claims(page)
            unpublished_disclosure_findings = evaluator._verify_no_unpublished_disclosure(page)

            publish_claim_count += len(publish_claim_findings)
            unpublished_disclosure_count += len(unpublished_disclosure_findings)

            if publish_claim_findings and len(sample_publish_claim) < 3:
                f = publish_claim_findings[0]
                sample_publish_claim.append({"path": f.filepath, "message": f.message})
            if unpublished_disclosure_findings and len(sample_unpublished_disclosure) < 3:
                f = unpublished_disclosure_findings[0]
                sample_unpublished_disclosure.append({"path": f.filepath, "message": f.message})

        total_pages_checked += len(pages)
        if publish_claim_count or unpublished_disclosure_count:
            per_product.append({
                "family": family, "platform": platform,
                "pages_checked": len(pages),
                "publish_claim_contradiction_findings": publish_claim_count,
                "unpublished_disclosure_findings": unpublished_disclosure_count,
                "sample_publish_claim_contradiction": sample_publish_claim,
                "sample_unpublished_disclosure": sample_unpublished_disclosure,
            })
        total_publish_claim_findings += publish_claim_count
        total_unpublished_disclosure_findings += unpublished_disclosure_count

    return {
        "per_product": per_product,
        "total_pages_checked": total_pages_checked,
        "total_publish_claim_contradiction_findings": total_publish_claim_findings,
        "total_unpublished_disclosure_findings": total_unpublished_disclosure_findings,
    }


def _reconciliation_rows(
    literal_report: dict[str, Any], recipe_report: dict[str, Any], *, sweep_run_id: str, recorded_at: str,
) -> list[dict[str, Any]]:
    """Build one reconciliation-store row per (family, platform) touched by
    either sweep -- a product-level aggregate row (not one row per content
    page), matching PKGINSTALL-CONTENT-HEALING-STATUS-WRITEBACK's own
    established per-product row shape for this same store."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}

    for p in literal_report["per_product"]:
        key = (p["family"], p["platform"])
        rows[key] = {
            "path": f"reports/audit/install-defect-sweep/{p['family']}-{p['platform']}",
            "family": p["family"], "platform": p["platform"],
            "site": "portfolio", "locale": "en",
            "representation": "literal" if p["findings"] else "shortcode_block",
            "collision_classification": None,
            "finding_count_literal": p["findings"],
            "sweep_run_id": sweep_run_id, "recorded_at": recorded_at,
        }

    for p in recipe_report["per_product"]:
        key = (p["family"], p["platform"])
        row = rows.setdefault(key, {
            "path": f"reports/audit/install-defect-sweep/{p['family']}-{p['platform']}",
            "family": p["family"], "platform": p["platform"],
            "site": "portfolio", "locale": "en",
            "representation": "shortcode_block",
            "collision_classification": None,
            "finding_count_literal": 0,
            "sweep_run_id": sweep_run_id, "recorded_at": recorded_at,
        })
        row["finding_count_install_recipe_fail"] = (
            p["publish_claim_contradiction_findings"] + p["unpublished_disclosure_findings"]
        )

    return list(rows.values())


def _english_source_file_rows(
    *, registry: "dict[str, Any] | None" = None, sweep_run_id: str, recorded_at: str,
) -> list[dict[str, Any]]:
    """One real per-file reconciliation row for every ENGLISH-SOURCE content
    file the literal sweep scans -- the exact row shape (a real content/
    path, keyed exactly like locale_patch._reconciliation_key()'s own
    normalization) that is_english_source_ready() looks up, and that
    _reconciliation_rows()'s product-level aggregate above never provides.

    Scoped to locale == "en" only, deliberately not the full corpus a
    literal sweep otherwise checks (all locales): is_english_source_ready()
    is only ever consulted for the English source a locale-propagation
    caller is about to fix and propagate FROM (see locale_patch.py's own
    module docstring), never for an arbitrary locale copy -- so a locale
    copy's row would be real but never actually read by any legitimate
    caller. Confirmed live 2026-09-18: 918 English-source files vs 20,956
    total files across the full tracked-registry corpus -- restricting to
    this real, load-bearing subset keeps this writer's per-sweep row growth
    about 23x smaller than a full-corpus emission, with no loss of coverage
    for the one lookup shape that matters.

    representation mirrors _reconciliation_rows()'s own existing convention
    for this same store ("literal" if any literal finding, else
    "shortcode_block") so the aggregate and per-file views stay consistent
    from one sweep run rather than diverging on two different rules.
    collision_classification is left None, same as the aggregate rows --
    this sweep does not run collision classification; only a dedicated
    classifier pass (install_collision_classifier.py) can set that field.
    """
    data = registry if registry is not None else load_registry(install_literal_sweep._DATA_PATH)
    repo_root = install_literal_sweep._REPO_ROOT

    rows: list[dict[str, Any]] = []
    for family, platforms in sorted(data.items()):
        if not isinstance(platforms, dict):
            continue
        for platform, entry in sorted(platforms.items()):
            if not isinstance(entry, dict):
                continue
            if entry.get("registry_type") not in install_literal_sweep._TRACKED_REGISTRY_TYPES:
                continue
            for fp in install_literal_sweep._files_for(family, platform):
                locale = _locale_from_path(fp, family)
                if locale != "en":
                    continue
                try:
                    rel = fp.relative_to(repo_root)
                except ValueError:
                    rel = fp
                rel_parts = rel.parts
                site = rel_parts[1] if len(rel_parts) > 1 and rel_parts[0] == "content" else "unknown"
                findings = verify_package_install_literals(fp, family, platform, registry=data)
                rows.append({
                    "path": str(rel).replace("\\", "/"),
                    "family": family, "platform": platform,
                    "site": site, "locale": "en",
                    "representation": "literal" if findings else "shortcode_block",
                    "collision_classification": None,
                    "finding_count_literal": len(findings),
                    "sweep_run_id": sweep_run_id, "recorded_at": recorded_at,
                })
    return rows


def run_combined_sweep(
    *, registry: "dict[str, Any] | None" = None, products: "dict[tuple[str, str], list] | None" = None,
    store: "ReconciliationStore | None" = None, sweep_run_id: "str | None" = None,
) -> dict[str, Any]:
    """Run both sweeps and append their results into the reconciliation
    store under one shared sweep_run_id. Read-only against content/data --
    only ever writes to reports/package-reconciliation/."""
    sweep_run_id = sweep_run_id or f"install-defect-sweep-{uuid.uuid4().hex[:12]}"
    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    literal_report = run_literal_sweep(registry=registry)
    recipe_report = run_install_recipe_sweep(products=products)

    aggregate_rows = _reconciliation_rows(
        literal_report, recipe_report, sweep_run_id=sweep_run_id, recorded_at=recorded_at,
    )
    file_rows = _english_source_file_rows(registry=registry, sweep_run_id=sweep_run_id, recorded_at=recorded_at)
    rows = aggregate_rows + file_rows
    store = store or ReconciliationStore(repo_root=REPO_ROOT)
    rows_written = store.append_batch(rows) if rows else 0

    return {
        "sweep_run_id": sweep_run_id,
        "recorded_at": recorded_at,
        "literal_report": literal_report,
        "recipe_report": recipe_report,
        "reconciliation_rows_written": rows_written,
        "english_source_file_rows_written": len(file_rows),
    }


def defect_class_findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a run_combined_sweep() result into one row per
    (family, platform, defect_class) with a nonzero finding count --
    exactly the shape sync_tracked_issues.py's dedup key needs."""
    out: list[dict[str, Any]] = []
    for p in result["literal_report"]["per_product"]:
        if p["findings"]:
            out.append({
                "family": p["family"], "platform": p["platform"],
                "defect_class": _DEFECT_CLASS_LITERAL, "count": p["findings"],
                "sample": p.get("sample_findings", []),
            })
    for p in result["recipe_report"]["per_product"]:
        if p["publish_claim_contradiction_findings"]:
            out.append({
                "family": p["family"], "platform": p["platform"],
                "defect_class": _DEFECT_CLASS_PUBLISH_CLAIM, "count": p["publish_claim_contradiction_findings"],
                "sample": p.get("sample_publish_claim_contradiction", []),
            })
        if p["unpublished_disclosure_findings"]:
            out.append({
                "family": p["family"], "platform": p["platform"],
                "defect_class": _DEFECT_CLASS_UNPUBLISHED_DISCLOSURE, "count": p["unpublished_disclosure_findings"],
                "sample": p.get("sample_unpublished_disclosure", []),
            })
    return out


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="install_defect_sweep")
    parser.add_argument("--report-dir", metavar="PATH", help="Directory to persist the durable report into")
    parser.add_argument("--issues-out", metavar="PATH", help="Write the flattened per-defect-class findings as JSON")
    args = parser.parse_args(argv)

    result = run_combined_sweep()
    literal = result["literal_report"]
    recipe = result["recipe_report"]
    print(
        f"literal: files_checked={literal['total_files_checked']} "
        f"findings={literal['total_findings']} | "
        f"install_recipe: pages_checked={recipe['total_pages_checked']} "
        f"publish_claim_contradiction={recipe['total_publish_claim_contradiction_findings']} "
        f"unpublished_disclosure={recipe['total_unpublished_disclosure_findings']} | "
        f"reconciliation_rows_written={result['reconciliation_rows_written']} "
        f"(english_source_file_rows={result['english_source_file_rows_written']}) "
        f"sweep_run_id={result['sweep_run_id']}"
    )

    record = install_literal_sweep.write_report(literal, out_dir=Path(args.report_dir) if args.report_dir else None)
    print(f"report_json={record['json_path']}")
    print(f"report_md={record['md_path']}")

    findings = defect_class_findings(result)
    if args.issues_out:
        Path(args.issues_out).write_text(json.dumps(findings, indent=2), encoding="utf-8")

    total = (
        literal["total_findings"]
        + recipe["total_publish_claim_contradiction_findings"]
        + recipe["total_unpublished_disclosure_findings"]
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
