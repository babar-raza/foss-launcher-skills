"""EvalRunner — injectable evaluation orchestrator for content_eval.

TC-08 (MP-SR08): Extracted from cli.py._run_evaluate() to allow unit testing
without filesystem or knowledge-bootstrap side-effects.

The runner owns:
  - evaluator dispatch loop
  - knowledge caching (per product)
  - cross-page analysis coordination
  - grade writing

CLI state (argparse.Namespace) is kept in cli.py; the runner accepts only
plain-Python arguments so tests can call it without touching the CLI layer.

Usage (tests):
    from content_eval.runner import EvalRunner
    runner = EvalRunner(
        evaluator_names=["code_block_api"],
        output_root=tmp_path,
        knowledge_root=tmp_path / "knowledge",
    )
    report = runner.run(pages, write_grade=False)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import EVALUATOR_LOGIC_VERSION, EVALUATOR_VERSIONS
from .models import EvalReport, Finding


def _load_knowledge(family: str, platform: str, knowledge_root: Path | None = None):
    """Load Knowledge from knowledge_core; supports injected root for tests."""
    _HERE = Path(__file__).resolve().parent.parent
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    from knowledge_core import Knowledge  # noqa: E402
    return Knowledge(family, platform, knowledge_root=knowledge_root)


class EvalRunner:
    """Orchestrates evaluation of a list of pages.

    Parameters
    ----------
    evaluator_names : list[str]
        Evaluators to run (validated against ALL_EVALUATORS before first use).
    output_root : Path | str | None
        Override for the reports directory root.  If None, defaults to
        ``Path("reports") / "content_eval"``.
    knowledge_root : Path | str | None
        Override for the knowledge/ directory root.  If None, defaults to
        ``knowledge_core``'s own default (inferred from __file__).
    """

    def __init__(
        self,
        evaluator_names: list[str],
        output_root: "Path | str | None" = None,
        knowledge_root: "Path | str | None" = None,
    ) -> None:
        self.evaluator_names = list(evaluator_names)
        self.output_root = Path(output_root) if output_root is not None else None
        self.knowledge_root = Path(knowledge_root) if knowledge_root is not None else None

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def run(
        self,
        pages: list[Any],
        *,
        write_grade: bool = False,
        skip_graded: bool = False,
        cross_page: bool = False,
        target_str: str = "files",
        _seed_cache: "dict | None" = None,
    ) -> EvalReport:
        """Evaluate *pages* and return a populated EvalReport.

        Parameters
        ----------
        pages :
            Loaded ``Page`` objects (from ``loader.load_pages`` or ``load_files``).
        write_grade :
            If True, persist computed grades into each page's frontmatter.
        skip_graded :
            If True, filter out pages already graded at the current logic version
            and model SHA.
        cross_page :
            If True, run cross-page consistency and deduplication checks after
            the per-page loop.
        target_str :
            Human-readable scope label for EvalReport.scope.
        _seed_cache :
            Internal/CLI-composition seam.  If provided, pre-populates
            ``self.knowledge_cache`` with already-loaded Knowledge objects so
            callers that pre-load knowledge for skip-graded filtering (e.g.
            cli.py) avoid a redundant second load.  A *copy* is taken so
            mutations during run do not affect the caller's dict.  Not part of
            the public consumer API — do not rely on this in tests.
        """
        from .evaluators import _ensure_loaded, get_evaluator

        _ensure_loaded()

        report = EvalReport(
            evaluators_run=list(self.evaluator_names),
            scope={"target": target_str, "files": []},
        )

        # Cache knowledge per (family, platform) key — exposed as public attribute
        # so callers (e.g. cli.py sweep) can reuse loaded knowledge without reloading.
        # SR-01: seed from caller's pre-loaded cache to avoid double-loading when
        # cli.py skip-graded block already loaded knowledge for filtering.
        self.knowledge_cache: dict[tuple[str, str], object] = (
            dict(_seed_cache) if _seed_cache else {}
        )
        knowledge_cache = self.knowledge_cache
        unavailable_keys: set[tuple[str, str]] = set()
        enrichment_warned_keys: set[tuple[str, str]] = set()

        # Optional skip-graded filter
        if skip_graded:
            pages = self._filter_already_graded(pages, knowledge_cache)

        # Per-page evaluation
        for page in pages:
            key = (page.family, page.platform)
            if key not in knowledge_cache:
                if page.family and page.platform:
                    knowledge_cache[key] = _load_knowledge(
                        page.family, page.platform,
                        knowledge_root=self.knowledge_root,
                    )
                else:
                    knowledge_cache[key] = None

            knowledge = knowledge_cache[key]

            # Enrichment-status warning (RC-1 fix): emitted once per product when
            # enrichment is degraded so callers know claim-based findings may be inflated.
            if knowledge and key not in enrichment_warned_keys:
                enrichment_warned_keys.add(key)
                es = getattr(knowledge, "enrichment_status", None)
                if es is not None and es != "full":
                    family_w, platform_w = key
                    print(
                        f"[content_eval] WARNING: enrichment_status={es!r} for "
                        f"{family_w}/{platform_w}"
                        " — claim-based evaluators may report false gaps",
                        file=sys.stderr,
                    )

            if knowledge and not getattr(knowledge, "available", True):
                if key not in unavailable_keys:
                    unavailable_keys.add(key)
                    family, platform = key
                    report.findings.append(Finding(
                        level="FAIL",
                        category="PIPELINE",
                        filepath=str(page.filepath),
                        line_no=0,
                        message=(
                            f"Knowledge unavailable for {family}/{platform}. "
                            f"Run /knowledge-bootstrap {family} {platform} first. "
                            f"Grading without knowledge produces inflated grades."
                        ),
                        evaluator="runner",
                        suggestion="Run /knowledge-bootstrap to populate knowledge artifacts.",
                    ))
                report.pages_evaluated += 1
                continue

            for eval_name in self.evaluator_names:
                evaluator_cls = get_evaluator(eval_name)
                evaluator = evaluator_cls()
                try:
                    findings = evaluator.evaluate(page, knowledge)
                    report.findings.extend(findings)
                except Exception as exc:
                    import traceback as _tb
                    report.findings.append(Finding(
                        level="FAIL",
                        category="PIPELINE",
                        filepath=str(page.filepath),
                        line_no=0,
                        message=f"Evaluator '{eval_name}' raised {type(exc).__name__}: {exc}",
                        evaluator="runner",
                        suggestion="Check stderr for full traceback.",
                    ))
                    print(_tb.format_exc(), file=sys.stderr)

            report.pages_evaluated += 1

        # Cross-page analysis
        if cross_page:
            from .cross_page.consistency import check_consistency
            from .cross_page.deduplication import check_deduplication
            report.findings.extend(check_consistency(pages))
            report.evaluators_run.append("cross_page_consistency")
            report.findings.extend(check_deduplication(pages))
            report.evaluators_run.append("cross_dedup")

        # Grade writing
        if write_grade:
            self._write_grades(pages, report, knowledge_cache)

        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_already_graded(self, pages, knowledge_cache):
        """ARCH-02: Skip-graded gate — manifest first, frontmatter fallback.

        Checks the external grade manifest for a matching entry before falling
        back to frontmatter-based skip logic.  This avoids reading .md files
        when the manifest has current operational state.
        """
        _HERE = Path(__file__).resolve().parent.parent
        if str(_HERE) not in sys.path:
            sys.path.insert(0, str(_HERE))
        from grade_writer import read_grade as _read_grade, content_hash as _content_hash  # noqa
        from grade_manifest import load_manifest, manifest_skip_check  # noqa
        from core.markdown import _FRONTMATTER_WRITER_RE as _FM_RE  # noqa

        # Load manifest once for the entire filter pass
        manifest = load_manifest()

        filtered = []
        for page in pages:
            key = (page.family, page.platform)
            if key not in knowledge_cache:
                if page.family and page.platform:
                    knowledge_cache[key] = _load_knowledge(
                        page.family, page.platform,
                        knowledge_root=self.knowledge_root,
                    )
                else:
                    knowledge_cache[key] = None
            k = knowledge_cache[key]

            # Compute current content hash for comparison
            try:
                text = page.filepath.read_text(encoding="utf-8")
                fm_m = _FM_RE.match(text)
                body = text[fm_m.end():] if fm_m else text
                current_hash = _content_hash(body)
            except (OSError, UnicodeDecodeError):
                filtered.append(page)
                continue

            # ARCH-02: Try manifest first
            current_enrich = getattr(k, "enrichment_status", None) or "full"
            rel_path = str(page.filepath).replace("\\", "/")
            can_skip, _reason = manifest_skip_check(
                rel_path,
                current_content_hash=current_hash,
                current_evaluator_versions=EVALUATOR_VERSIONS,
                current_enrichment_status=current_enrich,
                evaluator_names=self.evaluator_names,
                manifest=manifest,
            )
            if can_skip:
                continue  # Manifest confirms page is current — skip

            # MIG-02 fallback: check frontmatter if manifest had no entry
            stored = _read_grade(page.filepath)
            if (stored and stored["tier"] == "full"
                    and k and hasattr(k, "repo_sha")
                    and stored["model_sha"] == k.repo_sha
                    and stored.get("logic_version", "") == EVALUATOR_LOGIC_VERSION):
                # RC-2 fix: enrichment quality gate.
                stored_enrich = stored.get("enrichment_status") or "full"
                if current_enrich != stored_enrich:
                    filtered.append(page)
                    continue
                stored_hash = stored.get("content_hash", "")
                if stored_hash and _content_hash(body) == stored_hash:
                    continue  # Frontmatter confirms page is current — skip
            filtered.append(page)
        return filtered

    def _write_grades(self, pages, report: EvalReport, knowledge_cache):
        """Write grades to frontmatter and manifest (ARCH-03)."""
        _HERE = Path(__file__).resolve().parent.parent
        if str(_HERE) not in sys.path:
            sys.path.insert(0, str(_HERE))
        from grade_writer import write_grade as _write_grade, content_hash as _content_hash  # noqa
        from grade_manifest import load_manifest, write_manifest_entry, save_manifest  # noqa
        from core.markdown import _FRONTMATTER_WRITER_RE as _FM_RE  # noqa

        # ARCH-03: Load manifest once, batch-update entries, save once at end
        manifest = load_manifest()

        by_file = report.by_file()
        for page in pages:
            fp = page.filepath
            page_findings = by_file.get(str(fp), [])
            page_report = EvalReport(page_findings)
            grade = page_report.grade
            reasons = page_report.grade_reasons()
            k = knowledge_cache.get((page.family, page.platform))
            model_sha = k.repo_sha if k and hasattr(k, "repo_sha") else ""
            tier = "full" if k and getattr(k, "available", False) else "structural"
            enrich_status = getattr(k, "enrichment_status", None) if k else None

            # Compute content hash for manifest entry
            try:
                text = fp.read_text(encoding="utf-8")
                fm_m = _FM_RE.match(text)
                body = text[fm_m.end():] if fm_m else text
                body_hash = _content_hash(body)
            except (OSError, UnicodeDecodeError):
                body_hash = ""

            # ARCH-03: Always write manifest entry (operational state)
            rel_path = str(fp).replace("\\", "/")
            write_manifest_entry(
                rel_path,
                content_hash=body_hash,
                grade=grade,
                grade_reasons=reasons,
                evaluator_versions=dict(EVALUATOR_VERSIONS),
                model_sha=model_sha,
                logic_version=EVALUATOR_LOGIC_VERSION,
                enrichment_status=enrich_status,
                graded_evaluators=tier,
                manifest=manifest,
                save=False,  # batch — save once at end
            )

            # Write frontmatter (respects write_mode from caller)
            _write_grade(fp, grade, model_sha=model_sha, evaluator_tier=tier,
                         logic_version=EVALUATOR_LOGIC_VERSION, grade_reasons=reasons,
                         enrichment_status=enrich_status)

        # ARCH-03: Persist manifest after all entries are written
        save_manifest(manifest)
