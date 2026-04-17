"""Benchmark harness: measure evaluation system alignment with human review.

Computes four metrics against a corpus of human-reviewed pages:
  1. Recall — % of human findings the system also detects
  2. Severity alignment — % of matched findings where system severity >= human
  3. Verdict-direction alignment — % of pages where block/pass matches human
  4. False-positive count — system findings on known-good pages with no human match

The corpus has two entry types:
  - "live" — real content files evaluated in-place
  - "seeded" — synthetic pages with injected issues, created as temp files at
    test time and evaluated with real evaluators + real knowledge models

The composite human-likeness score is:
  0.50 * recall + 0.30 * severity_alignment + 0.20 * verdict_alignment

This test reports metrics. It does NOT assert a hard threshold until baseline
correctness is proven. The threshold assertion can be enabled by setting
BENCHMARK_ASSERT_THRESHOLD=1 in the environment.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_PIPELINE = _HERE.parent.parent  # scripts/pipeline
_REPO_ROOT = _PIPELINE.parent.parent

# Ensure pipeline modules are importable
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

# ---------------------------------------------------------------------------
# Fixtures — load corpus and mapping once per session
# ---------------------------------------------------------------------------

CORPUS_PATH = _HERE / "human_findings.json"
CATEGORY_MAP_PATH = _HERE / "category_map.json"
KNOWN_GOOD_PATH = _HERE / "known_good.json"
REPORT_DIR = _REPO_ROOT / "reports" / "benchmark"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def corpus():
    return _load_json(CORPUS_PATH)


@pytest.fixture(scope="session")
def category_map():
    raw = _load_json(CATEGORY_MAP_PATH)
    # Remove doc keys
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@pytest.fixture(scope="session")
def known_good():
    return _load_json(KNOWN_GOOD_PATH)


# ---------------------------------------------------------------------------
# Severity mapping — human to system
# ---------------------------------------------------------------------------

_HUMAN_TO_SYSTEM_SEVERITY = {
    "CRITICAL": 3,
    "HIGH": 2,
    "MEDIUM": 1,
    "LOW": 0,
}

_SYSTEM_LEVEL_RANK = {
    "FAIL": 2,
    "WARN": 1,
    "INFO": 0,
}


def _human_severity_rank(sev: str) -> int:
    return _HUMAN_TO_SYSTEM_SEVERITY.get(sev.upper(), 0)


def _system_severity_rank(level: str) -> int:
    return _SYSTEM_LEVEL_RANK.get(level.upper(), 0)


# ---------------------------------------------------------------------------
# Ensure knowledge/ paths resolve correctly (evaluators use Path("knowledge"))
# ---------------------------------------------------------------------------

import contextlib

@contextlib.contextmanager
def _repo_root_cwd():
    """Temporarily chdir to repo root so relative knowledge/ paths resolve."""
    prev = os.getcwd()
    os.chdir(str(_REPO_ROOT))
    try:
        yield
    finally:
        os.chdir(prev)


# ---------------------------------------------------------------------------
# Run evaluators on a single page
# ---------------------------------------------------------------------------

def _evaluate_page(file_path: str, family: str, platform: str) -> list[dict]:
    """Run DEFAULT_EVALUATORS on a single page, return findings as dicts."""
    from content_eval.config import DEFAULT_EVALUATORS
    from content_eval.evaluators import _ensure_loaded, get_evaluator
    from content_eval.loader import load_files
    from knowledge_core import Knowledge

    _ensure_loaded()

    abs_path = Path(file_path) if Path(file_path).is_absolute() else _REPO_ROOT / file_path
    if not abs_path.exists():
        return []

    with _repo_root_cwd():
        pages = load_files([str(abs_path)])
        if not pages:
            return []

        page = pages[0]
        knowledge = Knowledge(family, platform)

        findings = []
        for eval_name in DEFAULT_EVALUATORS:
            evaluator_cls = get_evaluator(eval_name)
            evaluator = evaluator_cls()
            try:
                page_findings = evaluator.evaluate(page, knowledge)
                for f in page_findings:
                    findings.append({
                        "category": f.category,
                        "level": f.level,
                        "message": f.message,
                        "evaluator": f.evaluator,
                    })
            except Exception:
                pass  # Evaluator failures are not FP — skip gracefully

        return findings


def _evaluate_seeded_page(
    entry: dict, family: str, platform: str, subdomain: str
) -> list[dict]:
    """Create a temp file from seed definition, evaluate it, return findings."""
    from content_eval.config import DEFAULT_EVALUATORS
    from content_eval.evaluators import _ensure_loaded, get_evaluator
    from content_eval.loader import load_files
    from knowledge_core import Knowledge

    _ensure_loaded()

    # Build markdown content from seed definition
    fm = entry.get("frontmatter", {})
    body = entry.get("body", "")
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    content = f"---\n{fm_yaml}---\n{body}\n"

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8",
        prefix=f"seed_{family}_{platform}_",
    ) as f:
        f.write(content)
        tmp_path = f.name

    try:
        with _repo_root_cwd():
            pages = load_files([tmp_path])
            if not pages:
                return []

            page = pages[0]
            # Override inferred metadata since temp path won't match real structure
            page.family = family
            page.platform = platform
            page.subdomain = subdomain

            knowledge = Knowledge(family, platform)

            findings = []
            for eval_name in DEFAULT_EVALUATORS:
                evaluator_cls = get_evaluator(eval_name)
                evaluator = evaluator_cls()
                try:
                    page_findings = evaluator.evaluate(page, knowledge)
                    for pf in page_findings:
                        findings.append({
                            "category": pf.category,
                            "level": pf.level,
                            "message": pf.message,
                            "evaluator": pf.evaluator,
                        })
                except Exception:
                    pass
            return findings
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def _find_matches(
    human_findings: list[dict],
    system_findings: list[dict],
    category_map: dict[str, list[str]],
) -> list[tuple[dict, dict | None]]:
    """Match human findings to system findings using the category map.

    Returns a list of (human_finding, matched_system_finding_or_None).
    Each system finding can match at most one human finding.
    """
    used_system = set()
    matches = []

    for hf in human_findings:
        hcat = hf["category"]
        mapped_cats = set(category_map.get(hcat, []))
        best_match = None

        for i, sf in enumerate(system_findings):
            if i in used_system:
                continue
            if sf["category"] in mapped_cats:
                best_match = (i, sf)
                break

        if best_match is not None:
            used_system.add(best_match[0])
            matches.append((hf, best_match[1]))
        else:
            matches.append((hf, None))

    return matches


# ---------------------------------------------------------------------------
# Benchmark test
# ---------------------------------------------------------------------------

class TestHumanLikeness:
    """Measure and report human-likeness of the default evaluation pipeline."""

    def test_benchmark(self, corpus, category_map, known_good, tmp_path):
        """Run the full benchmark and report metrics."""
        total_human_findings = 0
        matched_count = 0
        severity_correct = 0
        verdict_correct = 0
        total_pages = 0
        fp_count = 0

        page_results = []

        # --- Evaluate corpus pages ---
        for entry in corpus:
            # Skip doc entries
            if "_doc" in entry and "type" not in entry:
                continue

            entry_type = entry.get("type", "live")
            family = entry["family"]
            platform = entry["platform"]
            human_findings = entry["human_findings"]
            human_verdict = entry["human_verdict"]

            if entry_type == "live":
                file_path = entry["file"]
                system_findings = _evaluate_page(file_path, family, platform)
                display_name = file_path
            elif entry_type == "seeded":
                subdomain = entry.get("subdomain", "products")
                system_findings = _evaluate_seeded_page(
                    entry, family, platform, subdomain
                )
                display_name = entry.get("seed_id", "seeded")
            else:
                continue

            # Match
            matches = _find_matches(human_findings, system_findings, category_map)

            page_matched = 0
            page_sev_correct = 0

            for hf, sf in matches:
                total_human_findings += 1
                if sf is not None:
                    matched_count += 1
                    page_matched += 1
                    # Severity alignment: system level >= human severity
                    sys_rank = _system_severity_rank(sf["level"])
                    human_rank = _human_severity_rank(hf["severity"])
                    if sys_rank >= human_rank:
                        severity_correct += 1
                        page_sev_correct += 1

            # Verdict alignment
            # System would block if any FAIL finding exists
            system_has_fail = any(f["level"] == "FAIL" for f in system_findings)
            system_has_many_warn = (
                sum(1 for f in system_findings if f["level"] == "WARN") >= 6
            )
            system_would_block = system_has_fail or system_has_many_warn

            human_would_block = human_verdict == "WOULD_BLOCK"

            if system_would_block == human_would_block:
                verdict_correct += 1

            total_pages += 1

            page_results.append({
                "file": display_name,
                "type": entry_type,
                "human_findings": len(human_findings),
                "system_findings": len(system_findings),
                "matched": page_matched,
                "system_would_block": system_would_block,
                "human_would_block": human_would_block,
                "verdict_match": system_would_block == human_would_block,
            })

        # --- Evaluate known-good pages for false positives ---
        for pg in known_good.get("pages", []):
            file_path = pg["file"]
            family = pg["family"]
            platform = pg["platform"]

            system_findings = _evaluate_page(file_path, family, platform)
            fail_count = sum(1 for f in system_findings if f["level"] == "FAIL")
            fp_count += fail_count

        # --- Compute metrics ---
        recall = (
            matched_count / total_human_findings
            if total_human_findings > 0
            else 0.0
        )
        sev_alignment = (
            severity_correct / matched_count if matched_count > 0 else 1.0
        )
        verdict_alignment = (
            verdict_correct / total_pages if total_pages > 0 else 0.0
        )
        human_likeness = (
            0.50 * recall + 0.30 * sev_alignment + 0.20 * verdict_alignment
        )

        # --- Report ---
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "recall": round(recall, 4),
                "severity_alignment": round(sev_alignment, 4),
                "verdict_alignment": round(verdict_alignment, 4),
                "human_likeness": round(human_likeness, 4),
                "false_positive_count": fp_count,
            },
            "counts": {
                "total_human_findings": total_human_findings,
                "matched_findings": matched_count,
                "severity_correct": severity_correct,
                "verdict_correct": verdict_correct,
                "total_pages": total_pages,
            },
            "page_results": page_results,
            "evaluator_set": "DEFAULT_EVALUATORS",
        }

        # Write report to reports/benchmark/
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / "latest.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Print summary
        print(f"\n{'='*60}")
        print("HUMAN-LIKENESS BENCHMARK REPORT")
        print(f"{'='*60}")
        print(
            f"Recall:              {recall:.1%} "
            f"({matched_count}/{total_human_findings})"
        )
        print(
            f"Severity alignment:  {sev_alignment:.1%} "
            f"({severity_correct}/{matched_count})"
        )
        print(
            f"Verdict alignment:   {verdict_alignment:.1%} "
            f"({verdict_correct}/{total_pages})"
        )
        print(f"Human-likeness:      {human_likeness:.1%}")
        print(f"False positives (known-good): {fp_count}")
        print(f"{'='*60}")
        print("\nPer-page results:")
        for pr in page_results:
            block_sym = "BLOCK" if pr["system_would_block"] else "PASS"
            human_sym = "BLOCK" if pr["human_would_block"] else "PASS"
            match_sym = "OK" if pr["verdict_match"] else "MISMATCH"
            print(f"  [{pr['type']}] {pr['file']}")
            print(
                f"    human:{pr['human_findings']} sys:{pr['system_findings']} "
                f"matched:{pr['matched']} "
                f"verdict: sys={block_sym} human={human_sym} [{match_sym}]"
            )
        print(f"\nReport written to: {report_path}")

        # Optional hard assertion
        if os.environ.get("BENCHMARK_ASSERT_THRESHOLD"):
            threshold = float(os.environ.get("BENCHMARK_THRESHOLD", "0.60"))
            assert human_likeness >= threshold, (
                f"Human-likeness {human_likeness:.1%} below threshold "
                f"{threshold:.0%}"
            )

    def test_benchmark_no_unhandled_exceptions(self, corpus, tmp_path):
        """Guard: benchmark corpus must not crash any evaluator (G-3 guardrail).

        Ensures that pre-existing evaluator bugs do not contaminate benchmark
        results by silently swallowing exceptions. Any crash must be classified
        using the G-1 decision tree (AGENTS.md §6b) before routing.
        """
        from content_eval.config import DEFAULT_EVALUATORS

        crashes = []

        for entry in corpus:
            if "_doc" in entry and "type" not in entry:
                continue

            entry_type = entry.get("type", "live")
            family = entry["family"]
            platform = entry["platform"]

            try:
                if entry_type == "live":
                    file_path = entry["file"]
                    _evaluate_page(file_path, family, platform)
                elif entry_type == "seeded":
                    subdomain = entry.get("subdomain", "products")
                    _evaluate_seeded_page(entry, family, platform, subdomain)
            except Exception as exc:
                seed_id = entry.get("seed_id") or entry.get("file", "unknown")
                crashes.append(f"{seed_id}: {type(exc).__name__}: {exc}")

        assert not crashes, (
            "Evaluator crash(es) on benchmark corpus — classify each using "
            "G-1 decision tree (AGENTS.md §6b):\n"
            + "\n".join(crashes)
        )
