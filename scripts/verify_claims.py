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
    "path.guard": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "path guard": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "forbidden": ("scripts/path_guard.py", "tests/test_path_guard.py"),
    "pre.write": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "pre_write": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "stale": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "knowledge model": ("scripts/pre_write.py", "tests/test_pre_write.py"),
    "audit": ("scripts/pipeline/audit.py", "tests/test_audit_hardening.py"),
    "evidence": ("scripts/materialize.py", "tests/test_materialize.py"),
    "schema": ("scripts/schema_validate.py", "tests/test_schema_validate.py"),
    "downgrade": ("scripts/pipeline/no_downgrade_guard.py", "tests/test_no_downgrade_guard.py"),
    "no.downgrade": ("scripts/pipeline/no_downgrade_guard.py", "tests/test_no_downgrade_guard.py"),
    "check.setup": ("scripts/check_setup.py", "tests/test_check_setup.py"),
    "setup": ("scripts/check_setup.py", "tests/test_check_setup.py"),
    "ops.log": ("scripts/ops_log.py", "tests/test_ops_log.py"),
    "verify": ("scripts/verify.py", "tests/test_verify.py"),
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
