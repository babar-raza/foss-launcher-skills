"""verify_claims.py — Trace capability claims in docs to executable tests.

Reads AGENTS.md and all skills/*.md files, extracts sentences containing
capability verbs (enforces, blocks, requires, verifies, must, prevents),
and for each claim attempts to find:
  1. An implementing script in scripts/
  2. A test file in tests/

Outputs a claim coverage report.

Usage:
    python scripts/verify_claims.py [--output-dir <dir>] [--fail-on-unverified]

Exit codes:
    0  All critical claims verified
    1  One or more critical unverified claims found
    2  Error
"""
import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = __import__("datetime").date.today().isoformat()

# Verbs that indicate a capability claim
CLAIM_VERBS = re.compile(
    r"\b(enforces?|blocks?|requires?|verifies?|must|prevents?|"
    r"detects?|validates?|rejects?|denies?|guards?)\b",
    re.IGNORECASE,
)

# Sentences shorter than this are likely headers or incomplete thoughts
MIN_CLAIM_LEN = 20

# Map claim keywords to likely implementing scripts + test files
SCRIPT_HINTS = {
    # Path guard / S-01
    "path.guard": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "path guard": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "path-guard": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "forbidden": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "s-01": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "write path": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "allowed write": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    # Pre-write / stale model
    "pre.write": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "pre_write": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "pre-write": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "stale": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "knowledge model": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    # Ground-check / audit / S-23
    "ground.check": ("scripts/pipeline/audit.py", "tests/test_audit_hardening.py"),
    "ground-check": ("scripts/pipeline/audit.py", "tests/test_audit_hardening.py"),
    "ground check": ("scripts/pipeline/audit.py", "tests/test_audit_hardening.py"),
    "s-23": ("scripts/pipeline/audit.py", "tests/test_audit_hardening.py"),
    "audit": ("scripts/pipeline/audit.py", "tests/test_audit_hardening.py"),
    "hard stop": ("scripts/pipeline/audit.py", "tests/test_audit_hardening.py"),
    # Evidence / materialize / S-44
    "evidence": ("scripts/materialize.py", "tests/test_materialize.py"),
    "materialize": ("scripts/materialize.py", "tests/test_materialize.py"),
    "s-44": ("scripts/materialize.py", "tests/test_materialize.py"),
    # Schema
    "schema": ("scripts/schema_validate.py", "tests/test_schema_validate.py"),
    # Downgrade guard
    "downgrade": ("scripts/pipeline/no_downgrade_guard.py", "tests/test_no_downgrade_guard.py"),
    "no.downgrade": ("scripts/pipeline/no_downgrade_guard.py", "tests/test_no_downgrade_guard.py"),
    # Setup
    "check.setup": ("scripts/check_setup.py", "tests/test_check_setup.py"),
    "setup": ("scripts/check_setup.py", "tests/test_check_setup.py"),
    # Ops log
    "ops.log": ("scripts/ops_log.py", "tests/test_ops_log.py"),
    # Verify / S-42
    "verify": ("scripts/verify.py", "tests/test_verify.py"),
    "s-42": ("scripts/verify.py", "tests/test_verify.py"),
    # Decide / S-43
    "decide": ("scripts/decide.py", "tests/test_decide.py"),
    "s-43": ("scripts/decide.py", "tests/test_decide.py"),
    # Mental model / S-45
    "mental.model": ("scripts/mental_model.py", "tests/test_mental_model.py"),
    "mental model": ("scripts/mental_model.py", "tests/test_mental_model.py"),
    "s-45": ("scripts/mental_model.py", "tests/test_mental_model.py"),
    # Scout / S-34
    "scout": ("scripts/scout.py", "tests/test_scout_units.py"),
    "repo.scout": ("scripts/scout.py", "tests/test_scout_units.py"),
    "s-34": ("scripts/scout.py", "tests/test_scout_units.py"),
    "api_surface": ("scripts/scout.py", "tests/test_scout_units.py"),
    # Knowledge diff / S-12
    "knowledge.diff": ("scripts/differ.py", "tests/test_differ.py"),
    "s-12": ("scripts/differ.py", "tests/test_differ.py"),
    # Knowledge update / S-14 — uses e2e pipeline as closest test
    "knowledge.update": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    "knowledge bootstrap": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    "s-14": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    # Content eval / S-25 — uses golden_conformance as closest test proxy
    "eval report": ("scripts/golden_conformance.py", "tests/test_golden_conformance.py"),
    "s-25": ("scripts/golden_conformance.py", "tests/test_golden_conformance.py"),
    "rubric report": ("scripts/golden_conformance.py", "tests/test_golden_conformance.py"),
    # Heal page / S-26 — uses audit hardening as closest test proxy
    "heal": ("scripts/pipeline/remediate.py", "tests/test_audit_hardening.py"),
    "s-26": ("scripts/pipeline/remediate.py", "tests/test_audit_hardening.py"),
    # Site plan / S-57 / S-87 / delta-site-plan — uses e2e pipeline tests
    "site.plan": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    "delta.site": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    "knowledge_delta": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    "s-57": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    "s-87": ("scripts/pipeline/refresh_knowledge.py", "tests/test_e2e_pipeline.py"),
    # Knowledge coverage audit / S-86 — uses e2e pipeline tests
    "knowledge.coverage": ("scripts/pipeline/knowledge_core.py", "tests/test_e2e_pipeline.py"),
    "s-86": ("scripts/pipeline/knowledge_core.py", "tests/test_e2e_pipeline.py"),
    "orphaned claim": ("scripts/pipeline/knowledge_core.py", "tests/test_e2e_pipeline.py"),
    # Knowledge enrich / S-61 — uses scout units as closest test
    "knowledge.enrich": ("scripts/scout.py", "tests/test_scout_units.py"),
    "s-61": ("scripts/scout.py", "tests/test_scout_units.py"),
    # Page draft / S-19
    "page.draft": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "s-19": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "s-10": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    # Page enhance / S-21
    "page.enhance": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "s-21": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "s-17": ("scripts/pipeline/content_eval/__main__.py", "tests/test_content_eval.py"),
    # Page update / S-20
    "page.update": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "s-20": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    # Diagnose skill failure / S-72
    "diagnose": ("scripts/validate_skills.py", "tests/test_validate_skills.py"),
    "governance failure": ("scripts/validate_skills.py", "tests/test_validate_skills.py"),
    "s-72": ("scripts/validate_skills.py", "tests/test_validate_skills.py"),
    "registry": ("scripts/validate_skills.py", "tests/test_validate_skills.py"),
    # Corpus scan / S-37
    "corpus": ("scripts/corpus_scan.py", "tests/test_corpus_scan_units.py"),
    "s-37": ("scripts/corpus_scan.py", "tests/test_corpus_scan_units.py"),
    # Golden conformance
    "golden": ("scripts/golden_conformance.py", "tests/test_golden_conformance.py"),
    "conformance": ("scripts/golden_conformance.py", "tests/test_golden_conformance.py"),
    # Merge / S-35
    "merge": ("scripts/merge.py", "tests/test_merge_units.py"),
    "s-35": ("scripts/merge.py", "tests/test_merge_units.py"),
    # Index / S-31
    "truth.index": ("scripts/index.py", "tests/test_index.py"),
    "s-31": ("scripts/index.py", "tests/test_index.py"),
    # Embed / S-15 — uses index tests as closest proxy
    "embed": ("scripts/embed.py", "tests/test_index.py"),
    "s-15": ("scripts/embed.py", "tests/test_index.py"),
    # Discover / S-39
    "discover": ("scripts/discover.py", "tests/test_discover.py"),
    "s-39": ("scripts/discover.py", "tests/test_discover.py"),
    # Batch remediate / S-40/S-41 — uses audit hardening as closest test
    "remediate": ("scripts/pipeline/remediate.py", "tests/test_audit_hardening.py"),
    "s-40": ("scripts/pipeline/remediate.py", "tests/test_audit_hardening.py"),
    "s-41": ("scripts/pipeline/remediate.py", "tests/test_audit_hardening.py"),
    # Content audit / S-32 — uses audit hardening as closest test
    "content.audit": ("scripts/pipeline/content_audit.py", "tests/test_audit_hardening.py"),
    "s-32": ("scripts/pipeline/content_audit.py", "tests/test_audit_hardening.py"),
    # Stale detect / S-13
    "stale.detect": ("scripts/differ.py", "tests/test_differ.py"),
    "s-13": ("scripts/differ.py", "tests/test_differ.py"),
    # Launcher adapter
    "launcher": ("scripts/launcher_adapter.py", "tests/test_launcher_adapter.py"),
    # Config loader
    "config": ("scripts/config_loader.py", "tests/test_config_loader.py"),
}


@dataclass
class Claim:
    source_file: str
    text: str
    critical: bool = False
    script: str | None = None
    test: str | None = None

    @property
    def status(self) -> str:
        if self.script and self.test:
            s_exists = (REPO_ROOT / self.script).exists()
            t_exists = (REPO_ROOT / self.test).exists()
            if s_exists and t_exists:
                return "VERIFIED"
            if s_exists:
                return "PARTIAL"
        return "UNVERIFIED"


def extract_claims(text: str, source: str) -> list[Claim]:
    """Extract capability claims from a markdown document."""
    claims = []
    # Split into sentences (rough)
    sentences = re.split(r"(?<=[.!?])\s+|(?<=\n)(?=#)|(?<=\n)(?=\d+\.)", text)
    for sentence in sentences:
        sentence = sentence.strip()
        # Skip very short, code blocks, headers
        if len(sentence) < MIN_CLAIM_LEN:
            continue
        if sentence.startswith(("```", "#", "|", "-", "*", ">")):
            continue
        if not CLAIM_VERBS.search(sentence):
            continue
        # Determine if critical (mentions specific scripts/skills by name)
        critical = bool(re.search(
            r"\b(S-\d+|path.guard|pre.write|audit|evidence|schema|ground.check)\b",
            sentence, re.IGNORECASE,
        ))
        # Find implementing hints
        script, test = None, None
        lower = sentence.lower()
        for keyword, (s, t) in SCRIPT_HINTS.items():
            if keyword.replace(".", " ") in lower or keyword.replace(".", "_") in lower:
                script = s
                test = t
                break
        claims.append(Claim(
            source_file=source,
            text=sentence[:200],
            critical=critical,
            script=script,
            test=test,
        ))
    return claims


def collect_all_claims(repo_root: Path) -> list[Claim]:
    """Collect claims from AGENTS.md and all skills/*.md files."""
    all_claims: list[Claim] = []
    sources = [repo_root / "AGENTS.md"]
    sources += sorted((repo_root / "skills").glob("*.md"))

    for src in sources:
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8", errors="ignore")
        rel = str(src.relative_to(repo_root))
        all_claims.extend(extract_claims(text, rel))

    return all_claims


def write_report(claims: list[Claim], output_dir: Path) -> Path:
    """Write claim coverage report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"claim-coverage-{TODAY}.md"

    verified = [c for c in claims if c.status == "VERIFIED"]
    partial = [c for c in claims if c.status == "PARTIAL"]
    unverified = [c for c in claims if c.status == "UNVERIFIED"]
    critical_unverified = [c for c in unverified if c.critical]

    lines = [
        f"# Claim Coverage Report — {TODAY}",
        "",
        "## Summary",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| VERIFIED (script + test) | {len(verified)} |",
        f"| PARTIAL (script, no test) | {len(partial)} |",
        f"| UNVERIFIED | {len(unverified)} |",
        f"| Critical unverified | {len(critical_unverified)} |",
        f"| Total claims | {len(claims)} |",
        "",
    ]

    if critical_unverified:
        lines += ["## Critical Unverified Claims", ""]
        for c in critical_unverified:
            lines.append(f"- **[{c.source_file}]** {c.text}")
        lines.append("")

    if partial:
        lines += ["## Partial Claims (script present, test missing)", ""]
        for c in partial[:20]:  # cap at 20
            lines.append(f"- [{c.source_file}] {c.text[:100]} → needs test in {c.test}")
        lines.append("")

    lines += [
        "## Verified Claims (sample)",
        "",
    ]
    for c in verified[:10]:
        lines.append(f"- [{c.source_file}] {c.text[:100]}")
    lines += [
        "",
        f"*Generated by scripts/verify_claims.py on {TODAY}*",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify capability claims in docs against tests")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "reports"),
                        help="Directory for report (default: reports/)")
    parser.add_argument("--fail-on-unverified", action="store_true",
                        help="Exit 1 if any critical unverified claims found")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON summary to stdout")
    args = parser.parse_args(argv)

    try:
        claims = collect_all_claims(REPO_ROOT)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    critical_unverified = [c for c in claims if c.status == "UNVERIFIED" and c.critical]
    unverified = [c for c in claims if c.status == "UNVERIFIED"]
    verified = [c for c in claims if c.status == "VERIFIED"]

    if args.json:
        import json
        summary = {
            "date": TODAY,
            "total": len(claims),
            "verified": len(verified),
            "unverified": len(unverified),
            "critical_unverified": len(critical_unverified),
        }
        print(json.dumps(summary, indent=2))
    else:
        report_path = write_report(claims, Path(args.output_dir))
        print(f"Claims: {len(claims)} total, {len(verified)} verified, "
              f"{len(unverified)} unverified ({len(critical_unverified)} critical)")
        print(f"Report: {report_path}")

    if args.fail_on_unverified and critical_unverified:
        print(f"FAIL: {len(critical_unverified)} critical unverified claim(s)", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
