"""marketing_truth_validator.py - Validate marketing claims in products pages.

Checks the products.aspose.org landing page for forbidden capability claims
not backed by the clone-cache source (XMP, PDF/A, etc.).

Exit codes:
    0 - all checks pass
    1 - one or more BLOCKER violations detected
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

_REPO_ROOT = Path(__file__).resolve().parents[4]

_XMP_RE = re.compile(r"XMP", re.IGNORECASE)
_PDFA_RE = re.compile(r"PDF/A", re.IGNORECASE)
_DIGSIG_RE = re.compile(r"digital signature", re.IGNORECASE)

_FORBIDDEN_CLAIMS: dict[str, list[dict]] = {
    "go": [
        {
            "pattern": _XMP_RE,
            "description": "XMP metadata (not in Go release: metadata.go has Info dict only)",
            "severity": "BLOCKER",
        },
        {
            "pattern": _PDFA_RE,
            "description": "PDF/A conformance (validate.go checks structural integrity only)",
            "severity": "BLOCKER",
        },
        {
            "pattern": _DIGSIG_RE,
            "description": "digital signatures (not in exported Go API surface)",
            "severity": "WARN",
        },
    ],
}


def _parse_frontmatter(text: str) -> dict:
    if not yaml or not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except Exception:
        return {}


def _get_body(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("---", 3)
    return text[end + 3:] if end != -1 else text


def check_products_page(family: str, platform: str) -> list[dict]:
    products_path = (
        _REPO_ROOT / "content" / "products.aspose.org" / "en" / family / platform / "_index.md"
    )
    if not products_path.exists():
        print(f"WARN: products page not found for {family}/{platform}", file=sys.stderr)
        return []

    text = products_path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    body = _get_body(text)
    findings: list[dict] = []

    for claim in _FORBIDDEN_CLAIMS.get(platform, []):
        matches = list(claim["pattern"].finditer(body))
        if matches:
            ctx = body[max(0, matches[0].start() - 40):matches[0].end() + 40].strip()
            findings.append({
                "file": str(products_path),
                "claim": claim["description"],
                "severity": claim["severity"],
                "example": ctx,
            })

    evidence = frontmatter.get("evidence", {})
    if isinstance(evidence, dict) and not evidence.get("apis"):
        findings.append({
            "file": str(products_path),
            "claim": "evidence.apis is empty",
            "severity": "WARN",
            "example": "",
        })

    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate marketing claims in products pages")
    ap.add_argument("family")
    ap.add_argument("platform")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    findings = check_products_page(args.family, args.platform)
    blockers = [f for f in findings if f["severity"] == "BLOCKER"]
    warns = [f for f in findings if f["severity"] == "WARN"]

    if not args.quiet:
        print(f"marketing_truth_validator - {args.family}/{args.platform}")
        print(f"Findings: {len(findings)} ({len(blockers)} BLOCKER, {len(warns)} WARN)")
        print()

    for finding in findings:
        level = finding["severity"]
        print(f"  [{level}] {finding['claim']}")
        if finding.get("example"):
            print(f"         context: ...{finding['example']}...")
        print(f"         in {finding['file']}")

    if blockers:
        print()
        print(f"RESULT: FAIL - {len(blockers)} BLOCKER violation(s) in marketing claims")
        return 1

    if not args.quiet:
        status = "PASS" if not warns else "PASS_WITH_WARNS"
        print(f"RESULT: {status} - no BLOCKER violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
