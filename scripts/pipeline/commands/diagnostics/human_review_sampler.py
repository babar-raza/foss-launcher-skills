# Adapted from aspose.org
"""Generate review samples for human review gates H-01 and H-02.

H-01: Random sample of 5 non-reference pages (docs, blog, kb, products).
H-02: Stratified sample of 10 reference pages by class complexity.
H-03/H-04/H-05: Generate empty sign-off templates (operator fills manually).

Output: reports/human-review/{family}-{platform}-{gate}-sample.md
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_DEFAULT_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", Path(__file__).resolve().parents[4]))
_ROOT = _DEFAULT_ROOT
_CONTENT = _ROOT / "content"
_REPORT_DIR = _ROOT / "reports" / "human-review"

# Configurable subdomain names — override via environment variables
_BLOG_SITE = os.environ.get("FOSS_BLOG_SITE", "blog")
_DOCS_SITE = os.environ.get("FOSS_DOCS_SITE", "docs")
_KB_SITE = os.environ.get("FOSS_KB_SITE", "kb")
_PRODUCTS_SITE = os.environ.get("FOSS_PRODUCTS_SITE", "products")
_REFERENCE_SITE = os.environ.get("FOSS_REFERENCE_SITE", "reference")


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _ROOT, _CONTENT, _REPORT_DIR
    _ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_ROOT
    _CONTENT = _ROOT / "content"
    _REPORT_DIR = _ROOT / "reports" / "human-review"

_SUBDOMAINS_NON_REF = [
    _DOCS_SITE,
    _BLOG_SITE,
    _KB_SITE,
    _PRODUCTS_SITE,
]

H01_SAMPLE_SIZE = 5
H02_SAMPLE_SIZE = 10


def _collect_non_reference_pages(family: str, platform: str) -> list[Path]:
    """Collect all EN non-reference pages for the product."""
    pages: list[Path] = []
    for site in _SUBDOMAINS_NON_REF:
        # Try multiple layout patterns (with and without domain suffix, with and without /en/)
        for site_dir in _CONTENT.iterdir() if _CONTENT.exists() else []:
            if not site_dir.is_dir():
                continue
            if site not in site_dir.name:
                continue
            if site == _BLOG_SITE:
                search_root = site_dir / family / platform
                if search_root.is_dir():
                    pages.extend(search_root.rglob("index.md"))
            elif site == _PRODUCTS_SITE:
                search_root = site_dir / "en" / family
                if search_root.is_dir():
                    pages.extend(search_root.rglob("*.md"))
                # Also try without /en/
                search_root = site_dir / family
                if search_root.is_dir():
                    pages.extend(search_root.rglob("*.md"))
            else:
                search_root = site_dir / "en" / family / platform
                if search_root.is_dir():
                    pages.extend(search_root.rglob("*.md"))
                search_root = site_dir / family / platform
                if search_root.is_dir():
                    pages.extend(search_root.rglob("*.md"))
    return pages


def _collect_reference_pages(family: str, platform: str) -> list[Path]:
    """Collect all EN reference pages for the product."""
    pages: list[Path] = []
    if not _CONTENT.exists():
        return pages
    for site_dir in _CONTENT.iterdir():
        if not site_dir.is_dir():
            continue
        if _REFERENCE_SITE not in site_dir.name:
            continue
        for search_root in [
            site_dir / "en" / family / platform,
            site_dir / family / platform,
        ]:
            if search_root.is_dir():
                pages.extend(search_root.rglob("*.md"))
    return pages


def _page_complexity(page: Path) -> str:
    """Estimate page complexity: high/medium/low based on file size."""
    try:
        size = page.stat().st_size
    except OSError:
        return "low"
    if size > 8000:
        return "high"
    elif size > 3000:
        return "medium"
    return "low"


def _stratified_sample(pages: list[Path], n: int) -> list[Path]:
    """Stratified sample by complexity tier: ~40% high, ~40% medium, ~20% low."""
    tiers: dict[str, list[Path]] = {"high": [], "medium": [], "low": []}
    for p in pages:
        tiers[_page_complexity(p)].append(p)

    targets = {"high": max(1, int(n * 0.4)), "medium": max(1, int(n * 0.4)),
               "low": max(1, n - max(1, int(n * 0.4)) - max(1, int(n * 0.4)))}

    sample: list[Path] = []
    for tier, count in targets.items():
        pool = tiers[tier]
        random.shuffle(pool)
        sample.extend(pool[:count])

    remaining = n - len(sample)
    if remaining > 0:
        all_remaining = [p for p in pages if p not in sample]
        random.shuffle(all_remaining)
        sample.extend(all_remaining[:remaining])

    return sample[:n]


def _read_grade(page: Path) -> str:
    """Read grade from frontmatter."""
    try:
        text = page.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return "?"
    m = re.search(r"^grade:\s*([A-F])\s*$", text, re.MULTILINE)
    return m.group(1) if m else "ungraded"


def _relative(page: Path) -> str:
    """Return path relative to repo root."""
    try:
        return str(page.relative_to(_ROOT)).replace("\\", "/")
    except ValueError:
        return str(page)


def _signoff_block(
    *,
    logic_version: str = "",
    pages_hash: str = "",
    evaluator_version: str = "",
) -> str:
    """Generate the YAML sign-off block with integrity binding fields."""
    integrity = ""
    if logic_version:
        integrity += f"\nlogic_version: \"{logic_version}\""
    if pages_hash:
        integrity += f"\npages_hash: \"{pages_hash}\""
    if evaluator_version:
        integrity += f"\nevaluator_version: \"{evaluator_version}\""
    return f"""
---

## Sign-Off

```yaml
# --- SIGN-OFF (fill in after review) ---
reviewer: ""
date: ""
result: ""  # PASS | FAIL | CONDITIONAL
notes: ""{integrity}
```

**Instructions**: Fill in the sign-off block above after completing the review.
The readiness scorecard reads this file to verify H-gate completion.
"""


def generate_h01(family: str, platform: str) -> Path:
    """Generate H-01 sample: 5 random non-reference pages."""
    pages = _collect_non_reference_pages(family, platform)
    if not pages:
        print(f"WARNING: No non-reference pages found for {family}/{platform}", file=sys.stderr)
        sample = []
    else:
        random.shuffle(pages)
        sample = pages[:H01_SAMPLE_SIZE]

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = _REPORT_DIR / f"{family}-{platform}-h01-sample.md"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    iso_week = date.today().isocalendar()[1]
    seed = hashlib.sha256(f"{family}/{platform}/w{iso_week}".encode()).hexdigest()[:8]

    page_paths_str = "\n".join(sorted(_relative(p) for p in sample))
    pages_hash = hashlib.sha256(page_paths_str.encode()).hexdigest()[:12]

    lines = [
        f"# H-01 Human Prose Review: {family}/{platform}\n",
        f"**Generated**: {now}",
        f"**Sample seed**: {seed} (ISO week {iso_week})",
        f"**Sample size**: {len(sample)} of {len(pages)} non-reference pages\n",
        "## Review Checklist\n",
        "For each page below, verify:\n",
        "- [ ] Prose is factually accurate (no hallucinated capabilities)",
        "- [ ] Grade matches your assessment (within 1 grade level)",
        "- [ ] No marketing language or unsupported superlatives",
        "- [ ] Code examples are syntactically plausible for the platform",
        "- [ ] Code examples compile/run without errors for the stated language",
        "- [ ] Install/setup instructions reference the correct package manager",
        "- [ ] Package name and version are accurate",
        "- [ ] Feature claims are supported by the FOSS source code",
        "- [ ] Format support tables match formats.json ground truth",
        "- [ ] Links to other subdomains use correct absolute URLs",
        "- [ ] No broken internal links or anchors",
        "- [ ] Page title and description are accurate and non-generic",
        "- [ ] License information is correct",
        "- [ ] No placeholder or template text remains\n",
        "## Sampled Pages\n",
        "| # | Page | Grade | Subdomain | Verdict |",
        "|---|------|-------|-----------|---------|",
    ]

    for i, p in enumerate(sample, 1):
        grade = _read_grade(p)
        rel = _relative(p)
        parts = rel.split("/")
        site = parts[1] if len(parts) > 1 else "unknown"
        verdict = f"grade={grade}" if grade not in ("?", "ungraded") else ""
        lines.append(f"| {i} | `{rel}` | {grade} | {site} | {verdict} |")

    lines.append("")
    lines.append(_signoff_block(pages_hash=pages_hash))

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def generate_h02(family: str, platform: str) -> Path:
    """Generate H-02 sample: 10 stratified reference pages."""
    pages = _collect_reference_pages(family, platform)
    if not pages:
        print(f"WARNING: No reference pages found for {family}/{platform}", file=sys.stderr)
        sample = []
    else:
        sample = _stratified_sample(pages, H02_SAMPLE_SIZE)

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = _REPORT_DIR / f"{family}-{platform}-h02-sample.md"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    page_paths_str = "\n".join(sorted(_relative(p) for p in sample))
    pages_hash = hashlib.sha256(page_paths_str.encode()).hexdigest()[:12]

    lines = [
        f"# H-02 Reference Accuracy Review: {family}/{platform}\n",
        f"**Generated**: {now}",
        f"**Sample size**: {len(sample)} of {len(pages)} reference pages",
        f"**Stratification**: ~40% high-complexity, ~40% medium, ~20% low\n",
        "## Review Checklist\n",
        "For each page below, verify against the source repository:\n",
        "- [ ] API class/member names match api_surface.json",
        "- [ ] Method signatures are correct (parameter types, return types)",
        "- [ ] Parameter names and default values are accurate",
        "- [ ] No hallucinated members or methods",
        "- [ ] Access modifiers are correct (public/protected/internal)",
        "- [ ] Inheritance hierarchy is accurate",
        "- [ ] Property types match source code",
        "- [ ] Enum values are complete and correctly named",
        "- [ ] Exception types are documented correctly",
        "- [ ] Namespace/package path is correct",
        "- [ ] Cross-references to related types are valid",
        "- [ ] Deprecation status matches source code",
        "- [ ] Code examples use correct API calls",
        "- [ ] No placeholder or stub content remains\n",
        "## Sampled Pages\n",
        "| # | Page | Grade | Complexity | Verdict |",
        "|---|------|-------|------------|---------|",
    ]

    for i, p in enumerate(sample, 1):
        grade = _read_grade(p)
        rel = _relative(p)
        complexity = _page_complexity(p)
        verdict = f"grade={grade}" if grade not in ("?", "ungraded") else ""
        lines.append(f"| {i} | `{rel}` | {grade} | {complexity} | {verdict} |")

    lines.append("")
    lines.append(_signoff_block(pages_hash=pages_hash))

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def generate_h03_h04_h05(family: str, platform: str) -> list[Path]:
    """Generate empty sign-off templates for H-03, H-04, H-05."""
    templates = {
        "h03": ("H-03 Format Table Spot-Check",
                "Verify format support tables against clone cache formats.json.\n\n"
                "- [ ] Format names match formats.json entries\n"
                "- [ ] Import/Export/Read/Write columns are accurate\n"
                "- [ ] No formats listed that the library does not support"),
        "h04": ("H-04 Link Validation",
                "Verify all cross-subdomain links resolve.\n\n"
                "- [ ] Hugo build succeeds with no broken link warnings\n"
                "- [ ] All cross-subdomain URLs use correct absolute https:// format\n"
                "- [ ] English URLs omit /en/ prefix"),
        "h05": ("H-05 License Accuracy",
                "Verify open source license claims match the upstream repo LICENSE file.\n\n"
                "- [ ] License type stated correctly (MIT, Apache 2.0, etc.)\n"
                "- [ ] No overstated permissions\n"
                "- [ ] Copyright holder matches repo"),
    }

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    outputs = []

    for gate, (title, checklist) in templates.items():
        out = _REPORT_DIR / f"{family}-{platform}-{gate}-sample.md"
        content = (
            f"# {title}: {family}/{platform}\n\n"
            f"**Generated**: {now}\n\n"
            f"## Review Checklist\n\n{checklist}\n"
            f"{_signoff_block()}"
        )
        out.write_text(content, encoding="utf-8")
        outputs.append(out)

    return outputs


def main():
    parser = argparse.ArgumentParser(description="Human Review Gate Sampler")
    parser.add_argument("--family", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--gate", required=True,
                        choices=["h01", "h02", "h03", "h04", "h05", "all"],
                        help="Which gate to generate samples for")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducible sampling")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    outputs: list[Path] = []

    if args.gate in ("h01", "all"):
        out = generate_h01(args.family, args.platform)
        outputs.append(out)
        print(f"H-01 sample: {out}")

    if args.gate in ("h02", "all"):
        out = generate_h02(args.family, args.platform)
        outputs.append(out)
        print(f"H-02 sample: {out}")

    if args.gate in ("h03", "all"):
        outs = generate_h03_h04_h05(args.family, args.platform)
        outputs.extend(outs)
        for o in outs:
            print(f"{o.stem.split('-')[-2].upper()} template: {o}")

    if args.gate == "h04":
        outs = [generate_h03_h04_h05(args.family, args.platform)[1]]
        outputs.extend(outs)

    if args.gate == "h05":
        outs = [generate_h03_h04_h05(args.family, args.platform)[2]]
        outputs.extend(outs)

    print(f"\n{len(outputs)} file(s) written to {_REPORT_DIR}/")
    print("Next: Review the sampled pages, fill in the sign-off blocks, "
          "then re-run readiness_scorecard.py")


if __name__ == "__main__":
    main()
