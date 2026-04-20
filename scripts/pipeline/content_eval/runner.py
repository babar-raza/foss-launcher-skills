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

from . import EVALUATOR_LOGIC_VERSION
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
        """
        from .evaluators import _ensure_loaded, get_evaluator

        _ensure_loaded()

        report = EvalReport(
            evaluators_run=list(self.evaluator_names),
            scope={"target": target_str, "files": []},
        )

        # Cache knowledge per (family, platform) key — exposed as public attribute
        # so callers (e.g. cli.py sweep) can reuse loaded knowledge without reloading.
        self.knowledge_cache: dict[tuple[str, str], object] = {}
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
        _HERE = Path(__file__).resolve().parent.parent
        if str(_HERE) not in sys.path:
            sys.path.insert(0, str(_HERE))
        from grade_writer import read_grade as _read_grade, content_hash as _content_hash  # noqa
        from core.markdown import _FRONTMATTER_WRITER_RE as _FM_RE  # noqa

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
            stored = _read_grade(page.filepath)
            if (stored and stored["tier"] == "full"
                    and k and hasattr(k, "repo_sha")
                    and stored["model_sha"] == k.repo_sha
                    and stored.get("logic_version", "") == EVALUATOR_LOGIC_VERSION):
                # RC-2 fix: enrichment quality gate.
                # Re-evaluate when knowledge enrichment improved on the same repo SHA
                # (e.g. scout-only bootstrap followed by successful enrichment run).
                # None in either position is treated as "full" for backward-compat.
                current_enrich = getattr(k, "enrichment_status", None) or "full"
                stored_enrich = stored.get("enrichment_status") or "full"
                if current_enrich != stored_enrich:
                    filtered.append(page)
                    continue
                stored_hash = stored.get("content_hash", "")
                if stored_hash:
                    try:
                        text = page.filepath.read_text(encoding="utf-8")
                        fm_m = _FM_RE.match(text)
                        body = text[fm_m.end():] if fm_m else text
                        if _content_hash(body) != stored_hash:
                            filtered.append(page)
                            continue
                    except (OSError, UnicodeDecodeError):
                        pass
                continue
            filtered.append(page)
        return filtered

    def _write_grades(self, pages, report: EvalReport, knowledge_cache):
        _HERE = Path(__file__).resolve().parent.parent
        if str(_HERE) not in sys.path:
            sys.path.insert(0, str(_HERE))
        from grade_writer import write_grade as _write_grade  # noqa

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
            # Persist enrichment_status at grading time so the skip-graded gate
            # can detect quality improvements on the same repo SHA (RC-2/RC-3 fix).
            enrich_status = getattr(k, "enrichment_status", None) if k else None
            _write_grade(fp, grade, model_sha=model_sha, evaluator_tier=tier,
                         logic_version=EVALUATOR_LOGIC_VERSION, grade_reasons=reasons,
                         enrichment_status=enrich_status)
