# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_metrics_no_secrets.py — CI gate: prevent secrets in metrics code, tests, and reports.

Scans metrics source files, tests, and reports/metrics/ for secret-like patterns.
Never prints matched secret values — only file path, line number, and pattern type.

Allowlists harmless fake test-fixture patterns that cannot be real credentials.

Usage:
    python scripts/ci/checks/check_metrics_no_secrets.py
    python scripts/ci/checks/check_metrics_no_secrets.py --json-output

Exit codes:
    0  No secrets found (or all findings are allowlisted)
    1  Non-allowlisted secret-like finding
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))))

# Files and directories to scan
_SCAN_TARGETS = [
    "scripts/pipeline/commands/ops/metrics_submitter.py",
    "scripts/pipeline/commands/ops/metrics_schema.py",
    "scripts/pipeline/commands/ops/metrics_event_ledger.py",
    "scripts/pipeline/commands/ops/run_metrics.py",
    "scripts/pipeline/commands/ops/metrics_payload_builder.py",
    "scripts/pipeline/commands/ops/submit_metrics.py",
    "scripts/pipeline/commands/ops/professionalize_client.py",
]

_SCAN_DIR_TARGETS = [
    "scripts/pipeline/tests",
    "scripts/ci/checks",
    "reports/metrics",
]

# Patterns that indicate a secret (compiled)
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE)),
    ("api_key_assign", re.compile(r"""\b(api[_-]?key|token)\b\s*=\s*["'][A-Za-z0-9._\-]{16,}["']""", re.IGNORECASE)),
    ("sk_prefixed", re.compile(r'\bsk-[A-Za-z0-9]{20,}\b')),
    ("ghp_token", re.compile(r'\bghp_[A-Za-z0-9]{36,}\b')),
    ("gcp_key", re.compile(r'\bAIzaSy[A-Za-z0-9_\-]{33,}\b')),
    ("token_query_param", re.compile(r'[?&](token|api_key|key)=[A-Za-z0-9._\-]{16,}', re.IGNORECASE)),
    ("agent_metrics_token_value", re.compile(
        r'AGENT_METRICS_TOKEN\s*=\s*["\'][A-Za-z0-9._\-]{8,}["\']',
        re.IGNORECASE,
    )),
    ("gpt_oss_key_value", re.compile(
        r'GPT_OSS_API_KEY\s*=\s*["\'][A-Za-z0-9._\-]{8,}["\']',
        re.IGNORECASE,
    )),
    ("llm_key_value", re.compile(
        r'LLM_API_KEY\s*=\s*["\'][A-Za-z0-9._\-]{8,}["\']',
        re.IGNORECASE,
    )),
]

# Allowlisted fake test patterns — strings that are clearly fake in test context
# These must be substrings of the matched value (not patterns)
_ALLOWLIST_VALUE_SUBSTRINGS = [
    "fake",
    "test-token",
    "test_token",
    "dummy",
    "mock",
    "placeholder",
    "example",
    "your-token",
    "my-token",
    "super-secret-bearer-token",  # explicit test fixture string
    "my-runtime-token",
    "custom_token",
    "fake-bearer",
    "not-a-real",
    "12345",
]

# Line markers that exempt a line from secret scanning (test fixtures)
_FIXTURE_MARKERS = [
    "# SECRETS_TEST_FIXTURE",
    "# secrets-test-fixture",
    "# nosec",
]

# File extensions to scan as text
_TEXT_EXTENSIONS = {".py", ".json", ".jsonl", ".md", ".yaml", ".yml", ".txt"}

# Always-skip paths
_SKIP_PATHS = {
    ".venv", "__pycache__", ".git", "node_modules",
    "reports/metrics/slice0-evidence-bundle.tar.gz",
    "reports/metrics/slice1-evidence-bundle.tar.gz",
    "reports/metrics/slice2-evidence-bundle.tar.gz",
    "reports/metrics/slice3-evidence-bundle.tar.gz",
    "reports/metrics/slice4-evidence-bundle.tar.gz",
    "reports/metrics/slice5-evidence-bundle.tar.gz",
    "reports/metrics/slice6-evidence-bundle.tar.gz",
    "reports/metrics/slice7-evidence-bundle.tar.gz",
    "reports/metrics/slice8-evidence-bundle.tar.gz",
    "reports/metrics/slice9-evidence-bundle.tar.gz",
    "reports/metrics/master-plan-challenge-evidence-bundle.tar.gz",
    "reports/metrics/metrics-independent-verification-bundle.tar.gz",
}


@dataclass
class SecretFinding:
    file: str
    line: int
    pattern_type: str
    # NOTE: matched value is NEVER stored or printed


@dataclass
class SecretsCheckResult:
    passed: bool = True
    findings: list[SecretFinding] = field(default_factory=list)
    files_scanned: int = 0
    allowlisted: int = 0


def _is_allowlisted(matched_text: str) -> bool:
    lower = matched_text.lower()
    for sub in _ALLOWLIST_VALUE_SUBSTRINGS:
        if sub.lower() in lower:
            return True
    return False


def _should_skip(path: Path, repo_root: Path) -> bool:
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    for skip in _SKIP_PATHS:
        if rel == skip or rel.startswith(skip + "/"):
            return True
    # Skip binary .tar.gz
    if path.suffix in (".gz", ".tar", ".zip", ".bin", ".pkl", ".pyc"):
        return True
    return False


def _scan_file(file_path: Path, rel_path: str) -> tuple[list[SecretFinding], int]:
    """Scan one file. Returns (findings, allowlisted_count)."""
    findings: list[SecretFinding] = []
    allowlisted = 0

    if file_path.suffix not in _TEXT_EXTENSIONS:
        return findings, allowlisted

    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings, allowlisted

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Skip pure comments
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        # Skip lines marked as test fixtures
        if any(marker in line for marker in _FIXTURE_MARKERS):
            continue
        for pattern_type, pattern_re in _SECRET_PATTERNS:
            m = pattern_re.search(line)
            if m:
                matched = m.group(0)
                if _is_allowlisted(matched):
                    allowlisted += 1
                else:
                    findings.append(SecretFinding(
                        file=rel_path,
                        line=lineno,
                        pattern_type=pattern_type,
                        # matched value intentionally NOT stored
                    ))
    return findings, allowlisted


def _collect_paths(root: Path) -> list[Path]:
    paths: list[Path] = []

    # Specific files
    for rel in _SCAN_TARGETS:
        p = root / rel
        if p.exists():
            paths.append(p)

    # Directories
    for rel_dir in _SCAN_DIR_TARGETS:
        d = root / rel_dir
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file():
                paths.append(f)

    return paths


def run_check(root: Path) -> SecretsCheckResult:
    result = SecretsCheckResult()
    seen: set[Path] = set()

    for file_path in _collect_paths(root):
        if file_path in seen:
            continue
        if _should_skip(file_path, root):
            continue
        seen.add(file_path)
        result.files_scanned += 1
        try:
            rel = file_path.relative_to(root).as_posix()
        except ValueError:
            rel = str(file_path)
        findings, allowlisted = _scan_file(file_path, rel)
        result.findings.extend(findings)
        result.allowlisted += allowlisted

    result.passed = len(result.findings) == 0
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan metrics files and reports for secret-like values.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json-output", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    result = run_check(_REPO_ROOT)

    if args.json_output:
        print(json.dumps({
            "passed": result.passed,
            "files_scanned": result.files_scanned,
            "findings_count": len(result.findings),
            "allowlisted_count": result.allowlisted,
            "findings": [
                {"file": f.file, "line": f.line, "pattern_type": f.pattern_type}
                for f in result.findings
            ],
        }, indent=2))
    else:
        print(f"check_metrics_no_secrets: scanned {result.files_scanned} files, "
              f"{result.allowlisted} allowlisted pattern(s)")
        if result.findings:
            print(f"FAIL — {len(result.findings)} secret-like finding(s) [values not printed]:")
            for f in result.findings:
                print(f"  {f.file}:{f.line}  [{f.pattern_type}]")
        else:
            print("PASS — no secrets detected")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
