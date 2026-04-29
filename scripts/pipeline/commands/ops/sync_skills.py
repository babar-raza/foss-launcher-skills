"""Skill sync checker: verify canonical skills/ matches all provider directories.

Compares content between:
  - skills/{slug}.md              (canonical source of truth)
  - .agents/skills/{slug}/SKILL.md (Codex CLI)
  - .claude/commands/{slug}.md     (Claude Code)
  - .kilocode/skills/{slug}/SKILL.md (Kilo Code)

Usage:
    python scripts/pipeline/sync_skills.py --check        # verify parity, exit 1 on drift
    python scripts/pipeline/sync_skills.py --report       # print detailed report
    python scripts/pipeline/sync_skills.py --list-ids     # list all skill IDs
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

# Ensure stdout handles Unicode on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent

CANONICAL_DIR = _REPO_ROOT / "skills"
PROVIDERS = {
    "agents": _REPO_ROOT / ".agents" / "skills",
    "claude": _REPO_ROOT / ".claude" / "commands",
    "kilocode": _REPO_ROOT / ".kilocode" / "skills",
}

# Skills that intentionally exist only in specific providers
KNOWN_EXCEPTIONS = {
    # Claude-only: translate router dispatches to translate-page/translate-batch
    ("claude", "translate"): "Claude meta-router for translate-page + translate-batch",
    # Claude-only: SEO review skill
    ("claude", "seo-review"): "Claude-only SEO review gate",
    # Claude uses unified 'translate' router instead of split skills
    ("claude", "translate-batch"): "Claude uses unified translate router",
    ("claude", "translate-page"): "Claude uses unified translate router",
}

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from _skill_constants import INTERNAL_SKILLS

_ID_RE = re.compile(r"^#\s+(S-\d+):")

# Documentation files that coexist with skills but are not skills themselves
_NON_SKILL_SLUGS: set[str] = {"readme"}


def _extract_id(text: str) -> str | None:
    """Extract S-XX ID from the skill file header (within first 1500 chars).

    Scans beyond line 1 to accommodate files that start with a CONTRACT comment
    block (e.g. <!-- CONTRACT: ... -->) before the # S-XX: heading.
    Limit raised from 500 to 1500 to handle long multi-line CONTRACT blocks.
    """
    for line in text[:1500].splitlines():
        m = _ID_RE.match(line)
        if m:
            return m.group(1)
    return None


def _strip_provider_wrapper(text: str) -> str:
    """Strip YAML frontmatter from provider files for content comparison."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()


def _strip_cross_skill_note(text: str) -> str:
    """Strip the cross-skill reference note that only providers have."""
    return re.sub(
        r"> Cross-skill references like.*?\n\n?", "", text
    ).strip()


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for comparison: strip wrapper, notes, whitespace.

    Normalization rules applied in order:
    1. Strip YAML frontmatter (provider files only)
    2. Strip cross-skill reference note (provider files only)
    3. Strip <!-- CONTRACT: ... --> blocks (provider files only)
    4. Remove $ARGUMENTS placeholder differences
    5. Normalize whitespace

    Note: Python venv path normalization was removed — canonical and mirrors
    must both use .venv/Scripts/python consistently. enforce_venv_python.py
    validates this; sync_providers.py propagates canonical to mirrors.
    """
    text = _strip_provider_wrapper(text)
    text = _strip_cross_skill_note(text)
    # Strip <!-- CONTRACT: ... --> comment blocks (multi-line)
    text = re.sub(r"<!--\s+CONTRACT:.*?-->", "", text, flags=re.DOTALL)
    # Remove $ARGUMENTS placeholder differences
    text = text.replace("$ARGUMENTS", "").strip()
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def discover_canonical() -> dict[str, Path]:
    """Return {slug: path} for all canonical skills."""
    result = {}
    for p in sorted(CANONICAL_DIR.glob("*.md")):
        slug = p.stem
        if slug.lower() in _NON_SKILL_SLUGS:
            continue
        result[slug] = p
    return result


def discover_provider(provider: str) -> dict[str, Path]:
    """Return {slug: path} for all skills in a provider directory."""
    base = PROVIDERS[provider]
    result = {}
    if provider == "claude":
        for p in sorted(base.glob("*.md")):
            if p.stem.lower() in _NON_SKILL_SLUGS:
                continue
            result[p.stem] = p
    else:
        for d in sorted(base.iterdir()):
            skill_file = d / "SKILL.md"
            if d.is_dir() and skill_file.exists():
                result[d.name] = skill_file
    return result


def check_parity() -> list[dict]:
    """Check canonical vs all providers. Return list of issues."""
    canonical = discover_canonical()
    issues = []

    for provider_name, provider_base in PROVIDERS.items():
        provider_skills = discover_provider(provider_name)

        # Check for missing skills (in canonical but not in provider)
        for slug in sorted(canonical):
            if slug not in provider_skills:
                if (provider_name, slug) in KNOWN_EXCEPTIONS:
                    continue
                if provider_name == "claude" and slug in INTERNAL_SKILLS:
                    continue
                issues.append({
                    "type": "missing_in_provider",
                    "provider": provider_name,
                    "slug": slug,
                    "detail": f"Canonical skill '{slug}' not found in {provider_name}",
                })
                continue

            # Both exist — compare normalized content for drift
            if (provider_name, slug) in KNOWN_EXCEPTIONS:
                continue
            canonical_text = _normalize_for_comparison(
                canonical[slug].read_text(encoding="utf-8", errors="replace")
            )
            provider_text = _normalize_for_comparison(
                provider_skills[slug].read_text(encoding="utf-8", errors="replace")
            )
            if canonical_text != provider_text:
                from difflib import unified_diff
                diff_lines = list(unified_diff(
                    canonical_text.splitlines(),
                    provider_text.splitlines(),
                    fromfile=f"canonical/{slug}.md",
                    tofile=f"{provider_name}/{slug}",
                    lineterm="",
                    n=3,
                ))
                issues.append({
                    "type": "content_drift",
                    "provider": provider_name,
                    "slug": slug,
                    "detail": f"Content drift in '{slug}' between canonical and {provider_name}",
                    "diff_preview": "\n".join(diff_lines[:40]),
                })

        # Check for orphan skills (in provider but not in canonical)
        for slug in sorted(provider_skills):
            if slug not in canonical:
                if (provider_name, slug) in KNOWN_EXCEPTIONS:
                    continue
                issues.append({
                    "type": "orphan_in_provider",
                    "provider": provider_name,
                    "slug": slug,
                    "detail": f"Provider skill '{slug}' in {provider_name} has no canonical source",
                })

    return issues


def list_skill_ids() -> list[tuple[str, str, str]]:
    """Return [(id, slug, title)] sorted by ID number."""
    canonical = discover_canonical()
    results = []
    for slug, path in canonical.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        skill_id = _extract_id(text) or "NONE"
        first_line = text.split("\n", 1)[0]
        # Extract title after "# S-XX: "
        title = re.sub(r"^#\s+S-\d+:\s*", "", first_line).strip()
        if not title:
            title = first_line.strip("# ").strip()
        results.append((skill_id, slug, title))

    def sort_key(item):
        sid = item[0]
        if sid == "NONE":
            return (999,)
        return (int(sid.split("-")[1]),)

    return sorted(results, key=sort_key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sync_skills",
        description="Verify canonical skills match provider directories.",
    )
    parser.add_argument("--check", action="store_true", help="Exit 1 on any drift")
    parser.add_argument("--report", action="store_true", help="Print detailed report")
    parser.add_argument("--list-ids", action="store_true", help="List all skill IDs")
    args = parser.parse_args(argv)

    if args.list_ids:
        skills = list_skill_ids()
        print(f"{'ID':<8} {'Slug':<25} Title")
        print("-" * 80)
        for sid, slug, title in skills:
            print(f"{sid:<8} {slug:<25} {title}")
        print(f"\nTotal: {len(skills)} skills")
        no_id = sum(1 for s in skills if s[0] == "NONE")
        if no_id:
            print(f"WARNING: {no_id} skills without IDs")
        return 0

    issues = check_parity()

    if args.report or args.check:
        canonical = discover_canonical()
        print(f"Canonical skills: {len(canonical)}")
        for name in PROVIDERS:
            provider_skills = discover_provider(name)
            print(f"  {name}: {len(provider_skills)} skills")

        if issues:
            print(f"\n{len(issues)} issue(s) found:")
            for issue in issues:
                if issue["type"] == "missing_in_provider":
                    marker = "MISSING"
                elif issue["type"] == "orphan_in_provider":
                    marker = "ORPHAN"
                else:
                    marker = "DRIFT"
                print(f"  [{marker}] {issue['provider']}: {issue['slug']}")
        else:
            print("\nPARITY CHECK: PASS — all providers match canonical")

    if args.check:
        return 1 if issues else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())