"""Verification Worker — deterministic content verification against PEF.

Usage:
    python scripts/verify.py {content-file-path}
    python scripts/verify.py --batch {family} {platform}
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import resolve_evidence_root as _resolve_evidence_root

EVIDENCE_ROOT = _resolve_evidence_root()

# Regex for evidence citation comments: <!-- evidence: claim_id=X ... -->
CITATION_RE = re.compile(
    r'<!--\s*evidence:\s*claim_id=([^\s]+)(?:\s+source=([^\s]+))?(?:\s+confidence=([^\s]+))?\s*-->',
    re.IGNORECASE,
)

# Regex for inline code references like `ClassName.method()`
API_REF_RE = re.compile(r'`([A-Z][a-zA-Z0-9_]*(?:\.[a-z_][a-zA-Z0-9_]*)?)\(`')

# Regex for code block class/method usage
CODE_BLOCK_RE = re.compile(r'```(?:python|csharp|java|typescript|javascript|cpp)?\n(.*?)```', re.DOTALL)

# Regex for format mentions in prose like "**DOCX**" or "DOCX format"
FORMAT_RE = re.compile(r'\b([A-Z]{2,5})\b(?:\s*(?:format|files?|documents?))?')


def _read_json(path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_citations(content):
    """Parse evidence citation comments from markdown content."""
    citations = []
    for match in CITATION_RE.finditer(content):
        citations.append({
            "claim_id": match.group(1),
            "source": match.group(2) or "",
            "confidence": match.group(3) or "",
        })
    return citations


def _extract_api_references(content):
    """Extract class.method references from code blocks and inline code."""
    refs = set()

    # From inline code
    for match in API_REF_RE.finditer(content):
        refs.add(match.group(1))

    # From code blocks — look for class instantiation and method calls
    for block_match in CODE_BLOCK_RE.finditer(content):
        block = block_match.group(1)
        # Match patterns like ClassName( or obj.method(
        for line in block.splitlines():
            # Class instantiation: Document(, Workbook(
            for m in re.finditer(r'([A-Z][a-zA-Z0-9_]+)\(', line):
                refs.add(m.group(1))
            # Method calls: obj.method_name(
            for m in re.finditer(r'\.([a-z_][a-zA-Z0-9_]*)\(', line):
                refs.add(m.group(1))

    return sorted(refs)


def _extract_format_claims(content):
    """Extract format names mentioned in prose (outside code blocks)."""
    # Remove code blocks first
    prose = CODE_BLOCK_RE.sub('', content)
    # Known document formats
    known_formats = {"DOCX", "PDF", "XLSX", "CSV", "RTF", "HTML", "PPTX", "ODS",
                     "DOC", "XLS", "PPT", "JSON", "XML", "TXT", "EPUB", "SVG",
                     "PNG", "JPG", "TIFF", "BMP", "GIF", "MD", "YAML"}
    found = set()
    for match in FORMAT_RE.finditer(prose):
        name = match.group(1)
        if name in known_formats:
            found.add(name)
    return sorted(found)


def _check_forbidden(content, forbidden_claims):
    """Check content against forbidden claims list."""
    violations = []
    content_lower = content.lower()
    for claim in forbidden_claims:
        if claim.lower() in content_lower:
            violations.append(claim)
    return violations


def _resolve_family_platform(content_path):
    """Extract family and platform from content file path structure."""
    parts = Path(content_path).parts
    # Look for patterns like .../en/{family}/{platform}/... or .../{family}/{platform}/...
    for i, part in enumerate(parts):
        if part == "en" and i + 2 < len(parts):
            return parts[i + 1], parts[i + 2]
        if part in ("docs.aspose.org", "blog.aspose.org", "kb.aspose.org",
                     "reference.aspose.org", "products.aspose.org"):
            # Next parts should be family/platform or en/family/platform
            remaining = parts[i + 1:]
            if remaining and remaining[0] == "en":
                remaining = remaining[1:]
            if len(remaining) >= 2:
                return remaining[0], remaining[1]
    return None, None


def verify_page(content_path, pef):
    """Verify a single content page against PEF. Returns verification report."""
    content_path = Path(content_path)
    if not content_path.exists():
        return {"error": f"Content file not found: {content_path}"}

    content = content_path.read_text(encoding="utf-8")
    family = pef.get("family", "")
    platform = pef.get("platform", "")

    # Build lookup indexes from PEF
    claim_ids = {c.get("claim_id", ""): c for c in pef.get("claims", []) if c.get("claim_id")}
    api_names = set()
    for entry in pef.get("api_surface", []):
        if isinstance(entry, dict):
            name = entry.get("name", "")
            if name:
                api_names.add(name)
            for m in entry.get("methods", []):
                if isinstance(m, dict):
                    api_names.add(m.get("name", ""))
    format_names = set()
    for f in pef.get("formats", []):
        if isinstance(f, dict):
            name = f.get("format", f.get("name", ""))
            if name:
                format_names.add(name.upper())
    forbidden = pef.get("forbidden_claims", [])

    # Extract and verify
    citations = _extract_citations(content)
    api_refs = _extract_api_references(content)
    format_claims = _extract_format_claims(content)
    forbidden_violations = _check_forbidden(content, forbidden)

    # Citation verification
    valid_citations = [c for c in citations if c["claim_id"] in claim_ids]
    orphaned_citations = [c for c in citations if c["claim_id"] not in claim_ids]

    # API reference verification
    verified_api = [r for r in api_refs if r in api_names]
    unverified_api = [r for r in api_refs if r not in api_names]

    # Format verification
    confirmed_formats = [f for f in format_claims if f in format_names]
    contradicted_formats = []  # Would need deeper analysis

    # Code block analysis
    code_blocks = CODE_BLOCK_RE.findall(content)

    # Count API usage in code blocks
    code_api_count = 0
    for block in code_blocks:
        for name in api_names:
            if name in block:
                code_api_count += 1
                break

    # Build issues list
    issues = []
    for c in orphaned_citations:
        issues.append({
            "severity": "WARN",
            "type": "orphaned_citation",
            "detail": f"claim_id={c['claim_id']} not found in PEF",
            "line": None,
        })
    for name in unverified_api:
        issues.append({
            "severity": "WARN",
            "type": "unverified_api",
            "detail": f"API reference '{name}' not in PEF api_surface",
            "line": None,
        })
    for v in forbidden_violations:
        issues.append({
            "severity": "FAIL",
            "type": "forbidden_violation",
            "detail": f"Content references forbidden claim: {v}",
            "line": None,
        })

    # Compute grounded percentage
    total_checkable = len(citations) + len(api_refs)
    grounded_count = len(valid_citations) + len(verified_api)
    grounded_pct = round(grounded_count / total_checkable * 100, 1) if total_checkable > 0 else 100.0

    # Determine result
    if forbidden_violations:
        result = "FAIL"
    elif grounded_pct < 70:
        result = "FAIL"
    elif orphaned_citations or unverified_api:
        result = "WARN"
    else:
        result = "PASS"

    slug = content_path.stem
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    report = {
        "schema_version": 1,
        "content_path": str(content_path),
        "family": family,
        "platform": platform,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "pef_sha": pef.get("source_sha", ""),
        "citations": {
            "total": len(citations),
            "valid": len(valid_citations),
            "orphaned": len(orphaned_citations),
            "outdated": 0,
            "orphaned_ids": [c["claim_id"] for c in orphaned_citations],
            "outdated_ids": [],
        },
        "api_references": {
            "total": len(api_refs),
            "verified": len(verified_api),
            "unverified": len(unverified_api),
            "unverified_names": unverified_api,
        },
        "format_claims": {
            "total": len(format_claims),
            "confirmed": len(confirmed_formats),
            "contradicted": len(contradicted_formats),
            "contradicted_details": [],
        },
        "forbidden_violations": forbidden_violations,
        "code_blocks": {
            "total": len(code_blocks),
            "verified_api": code_api_count,
            "unverified": len(code_blocks) - code_api_count,
        },
        "result": result,
        "grounded_pct": grounded_pct,
        "issues": issues,
    }

    # Write report
    verify_dir = EVIDENCE_ROOT / family / platform / "verification"
    verify_dir.mkdir(parents=True, exist_ok=True)
    report_path = verify_dir / f"{slug}-{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {result}: {content_path.name} — grounded={grounded_pct}%, "
          f"citations={len(valid_citations)}/{len(citations)}, "
          f"api={len(verified_api)}/{len(api_refs)}")

    return report


def _load_pef(family, platform):
    pef_path = EVIDENCE_ROOT / family / platform / "pef.json"
    if not pef_path.exists():
        print(f"ERROR: No PEF found at {pef_path}. Run materialize first.")
        return None
    return json.loads(pef_path.read_text(encoding="utf-8"))


def batch_verify(family, platform, content_root=None):
    """Verify all content pages for a family/platform."""
    pef = _load_pef(family, platform)
    if not pef:
        return []

    if content_root is None:
        content_root = Path("output/content")

    site_paths = {
        "docs": content_root / "docs.aspose.org" / "en" / family / platform,
        "blog": content_root / "blog.aspose.org" / family / platform,
        "kb": content_root / "kb.aspose.org" / "en" / family / platform,
        "reference": content_root / "reference.aspose.org" / "en" / family / platform,
    }

    reports = []
    for site_type, base_path in site_paths.items():
        if not base_path.exists():
            continue
        for md_file in sorted(base_path.rglob("*.md")):
            if md_file.stem == "_index":
                continue
            report = verify_page(md_file, pef)
            reports.append(report)

    return reports


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/verify.py {content-file-path}")
        print("  python scripts/verify.py --batch {family} {platform}")
        sys.exit(1)

    if sys.argv[1] == "--batch":
        if len(sys.argv) < 4:
            print("Usage: python scripts/verify.py --batch {family} {platform}")
            sys.exit(1)
        reports = batch_verify(sys.argv[2], sys.argv[3])
        if not reports:
            print("No content pages found to verify.")
            sys.exit(1)
        pass_count = sum(1 for r in reports if r.get("result") == "PASS")
        warn_count = sum(1 for r in reports if r.get("result") == "WARN")
        fail_count = sum(1 for r in reports if r.get("result") == "FAIL")
        print(f"\nBatch: {len(reports)} pages — PASS={pass_count} WARN={warn_count} FAIL={fail_count}")
    else:
        content_path = Path(sys.argv[1])
        family, platform = _resolve_family_platform(content_path)
        if not family or not platform:
            print(f"ERROR: Cannot determine family/platform from path: {content_path}")
            sys.exit(1)
        pef = _load_pef(family, platform)
        if not pef:
            sys.exit(1)
        report = verify_page(content_path, pef)
        if report.get("result") == "FAIL":
            sys.exit(1)

    print("EVIDENCE-VERIFY: DONE")


if __name__ == "__main__":
    main()
