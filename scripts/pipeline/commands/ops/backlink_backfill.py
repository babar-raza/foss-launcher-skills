#!/usr/bin/env python3
# Adapted from aspose.org
"""backlink_backfill.py — Backlink insertion engine for aspose.org English content (TC-BL-005/006).

Reads the backlink audit report and inserts missing backlinks into in-scope English
content files. Operates in dry-run mode by default (no file writes).

Supports:
  - products.aspose.org: YAML overview.content insertion (PyYAML round-trip)
  - docs.aspose.org: Markdown See Also section insertion
  - kb.aspose.org: Markdown See Also section insertion
  - reference.aspose.org: Markdown See Also section insertion
  - blog.aspose.org: Markdown Related Resources section insertion

Usage:
    python scripts/pipeline/commands/ops/backlink_backfill.py           # dry-run all
    python scripts/pipeline/commands/ops/backlink_backfill.py --write   # apply writes
    python scripts/pipeline/commands/ops/backlink_backfill.py --family words --platform python
    python scripts/pipeline/commands/ops/backlink_backfill.py --subdomain docs.aspose.org
    python scripts/pipeline/commands/ops/backlink_backfill.py --family words --write

Exit codes:
    0   Success (dry-run or write complete)
    1   Fatal error (target map missing, products YAML round-trip failure, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import Optional

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import (
    COMPLIANT,
    PageType,
    classify_compliance,
    classify_page_type,
    count_qualifying_com_links,
    load_target_map,
    resolve_backlink,
)

SCRIPT_VERSION = "1.0.0"

# ──────────────────────────────────────────────────────────────────────────────
# Safety constants (§8.3)
# ──────────────────────────────────────────────────────────────────────────────

MAX_QUALIFYING_LINKS = 2   # never add if already at this count
# Process MISSING and WRONG_TARGET (has aspose.com links but none match accepted targets).
# For WRONG_TARGET: add correct target link if existing_count < MAX_QUALIFYING_LINKS.
BACKFILL_STATUSES = frozenset({"MISSING", "WRONG_TARGET"})

# Sections to create for each subdomain
SEE_ALSO_HEADER = "## See Also"
RELATED_RESOURCES_HEADER = "## Related Resources"


@dataclass
class BackfillChange:
    file: str             # repo-relative path
    subdomain: str
    family: str | None
    platform: str | None
    page_type: str
    target_url: str
    action: str           # "yaml_overview" | "md_see_also" | "md_related_resources"
    before_snippet: str   # first 200 chars of original content
    after_snippet: str    # first 200 chars of new content
    skipped: bool = False
    skip_reason: str = ""
    dry_run: bool = True


@dataclass
class BackfillManifest:
    generated_at: str
    generator: str
    dry_run: bool
    total_candidates: int
    total_modified: int
    total_skipped: int
    total_errors: int
    changes: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    rollback_commands: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Products YAML insertion (§5.1 / TC-BL-005)
# ──────────────────────────────────────────────────────────────────────────────

def backfill_products_yaml(
    file_path: Path,
    target_url: str,
    family: str,
    platform: str | None,
    families_map: dict,
    platforms_map: dict,
    *,
    dry_run: bool = True,
    target_type: str | None = None,
) -> BackfillChange:
    """Insert backlink into products.aspose.org YAML overview.content.

    target_type: "platform" or "family" — controls anchor text generation.
    """
    rel = file_path.relative_to(_REPO_ROOT).as_posix()
    raw = file_path.read_text(encoding="utf-8")

    # Parse frontmatter
    fm_text = raw
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            fm_text = raw[3:end]

    try:
        import yaml as _yaml
        data = _yaml.safe_load(fm_text)
    except Exception as exc:
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=raw[:200], after_snippet="",
            skipped=True, skip_reason=f"YAML parse failed: {exc}", dry_run=dry_run,
        )

    if not isinstance(data, dict):
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=raw[:200], after_snippet="",
            skipped=True, skip_reason="YAML did not parse to dict", dry_run=dry_run,
        )

    # Get existing overview.content
    overview = data.get("overview", {}) or {}
    current_content = overview.get("content", "") or ""

    # Idempotency: check if target URL already present
    if target_url.rstrip("/") in current_content:
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=current_content[:200], after_snippet=current_content[:200],
            skipped=True, skip_reason="Already contains target URL (idempotent)", dry_run=dry_run,
        )

    # Max-link guard
    link_count, _ = count_qualifying_com_links(current_content)
    if link_count >= MAX_QUALIFYING_LINKS:
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=current_content[:200], after_snippet="",
            skipped=True, skip_reason=f"Already at max links ({link_count})", dry_run=dry_run,
        )

    # Try to get LLM-generated copy first
    new_content = _get_llm_copy_for_file(rel, current_content, target_url,
                                          family, platform, families_map, platforms_map,
                                          target_type=target_type)

    # Validate new_content has exactly 1 new link to target
    if not _validate_overview_update(current_content, new_content, target_url):
        # Generate fresh template sentence as fallback
        new_content = _apply_overview_template(current_content, target_url,
                                                family, platform, families_map, platforms_map,
                                                target_type=target_type)

    if not dry_run:
        # Modify data dict
        if "overview" not in data or not isinstance(data.get("overview"), dict):
            data["overview"] = {}
        data["overview"]["content"] = new_content

        # Round-trip through PyYAML to preserve style
        new_raw = _rewrite_yaml_file(raw, data, fm_text)
        if new_raw is None:
            return BackfillChange(
                file=rel, subdomain="products.aspose.org", family=family, platform=platform,
                page_type="products-plugin" if platform else "products-family",
                target_url=target_url, action="yaml_overview",
                before_snippet=current_content[:200], after_snippet="",
                skipped=True, skip_reason="YAML round-trip failed", dry_run=dry_run,
            )
        file_path.write_text(new_raw, encoding="utf-8")

    return BackfillChange(
        file=rel, subdomain="products.aspose.org", family=family, platform=platform,
        page_type="products-plugin" if platform else "products-family",
        target_url=target_url, action="yaml_overview",
        before_snippet=current_content[:200], after_snippet=new_content[:200],
        dry_run=dry_run,
    )


def _get_llm_copy_for_file(
    rel_path: str,
    current_content: str,
    target_url: str,
    family: str,
    platform: str | None,
    families_map: dict,
    platforms_map: dict,
    target_type: str | None = None,
) -> str:
    """Get LLM-generated copy for a specific file from the generation report."""
    report_path = _REPO_ROOT / "reports" / "backlinks" / "products_llm_copy_generation.json"
    if report_path.exists():
        try:
            records = json.loads(report_path.read_text(encoding="utf-8"))
            for rec in records:
                if rec.get("file_path") == rel_path:
                    output = rec.get("output_text")
                    if output and output != current_content:
                        return output
        except Exception:
            pass
    return _apply_overview_template(current_content, target_url, family, platform, families_map, platforms_map,
                                    target_type=target_type)


def _validate_overview_update(original: str, updated: str, target_url: str) -> bool:
    """Validate that the updated text contains the target URL and is reasonable."""
    if not updated or updated == original:
        return False
    if target_url.rstrip("/") not in updated:
        return False
    # Check non-link retention >= 80% (permissive for backfill)
    stripped_orig = re.sub(r'\[[^\]]+\]\([^)]+\)', '', original).strip()
    stripped_upd = re.sub(r'\[[^\]]+\]\([^)]+\)', '', updated).strip()
    if len(stripped_orig) > 0:
        ratio = len(stripped_upd) / len(stripped_orig)
        if ratio < 0.80:
            return False
    return True


def _apply_overview_template(
    current_content: str,
    target_url: str,
    family: str,
    platform: str | None,
    families_map: dict,
    platforms_map: dict,
    target_type: str | None = None,
) -> str:
    """Apply template fallback to generate updated overview.content.

    target_type: "platform" or "family". When "family", anchor omits platform suffix.
    """
    fam_title = families_map.get(family, f"Aspose.{family.title()}")
    # FAMILY-ANCHOR rule: if resolved target is a family URL, never include "for {Platform}"
    if platform and target_type != "family":
        plat_title = platforms_map.get(platform, platform.title())
        display = f"{fam_title} for {plat_title}"
    else:
        display = fam_title

    # Measure word count
    wc = len(current_content.split())

    if not platform:
        sentence = f"For the complete commercial product family with dedicated support, visit [{display}]({target_url})."
    elif wc <= 140:
        sentence = f"The commercial counterpart is [{display}]({target_url})."
    else:
        sentence = (
            f"Developers who need the complete commercial API with full production support can use "
            f"[{display}]({target_url}) alongside these open-source resources."
        )

    text = current_content.rstrip()

    # Find insertion point before MIT/GitHub closing sentence
    closing_patterns = [r'[Ii]t is MIT', r'[Oo]pen.source on GitHub', r'MIT license', r'GitHub']
    sentences = list(re.finditer(r'(?<=[.!?])\s+(?=[A-Z])', text))
    insert_at = len(text)
    for pattern in closing_patterns:
        for m in reversed(sentences):
            tail = text[m.end():]
            if re.search(pattern, tail[:100]):
                insert_at = m.end()
                break
        if insert_at < len(text):
            break

    if insert_at >= len(text):
        return text + " " + sentence
    else:
        return text[:insert_at].rstrip() + " " + sentence + " " + text[insert_at:].lstrip()


def _rewrite_yaml_file(raw: str, data: dict, fm_text: str) -> str | None:
    """Rewrite the raw file preserving frontmatter structure."""
    try:
        import yaml as _yaml

        # Dump modified data back to YAML
        new_fm = _yaml.dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=10000,
        )

        # Reconstruct file: --- + new_fm + --- + (body if any)
        if raw.startswith("---"):
            end_idx = raw.find("---", 3)
            if end_idx != -1:
                body = raw[end_idx + 3:]  # everything after closing ---
                return f"---\n{new_fm}---{body}"

        return f"---\n{new_fm}---\n"
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Markdown section insertion (§5.2/5.3/5.4/5.5 / TC-BL-006)
# ──────────────────────────────────────────────────────────────────────────────

def _build_see_also_entry(
    target_url: str,
    family: str,
    platform: str | None,
    subdomain: str,
    families_map: dict,
    platforms_map: dict,
    target_type: str | None = None,
) -> str:
    """Build the See Also / Related Resources list entry.

    target_type: "platform" (use family+platform anchor) or "family" (use family-only anchor).
    When target_type is "family", platform is omitted from anchor text regardless of source platform.
    """
    fam_title = families_map.get(family, f"Aspose.{family.title()}")
    # FAMILY-ANCHOR rule: if resolved target is a family URL, never include "for {Platform}"
    if platform and target_type != "family":
        plat_title = platforms_map.get(platform, platform.title())
        display = f"{fam_title} for {plat_title}"
    else:
        display = fam_title

    link_text = f"{display} \u2014 Commercial Edition"
    return f"- [{link_text}]({target_url})"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split file into (frontmatter_block, body). frontmatter_block includes delimiters."""
    if not text.startswith("---"):
        return "", text
    end = text.find("---", 3)
    if end == -1:
        return "", text
    fm = text[:end + 3]
    body = text[end + 3:]
    return fm, body


def _is_inside_code_fence(text: str, pos: int) -> bool:
    """Check if position is inside a ``` code fence."""
    prefix = text[:pos]
    fence_count = len(re.findall(r'```', prefix))
    return fence_count % 2 == 1


def _find_section(body: str, header_re: str) -> tuple[int, int] | None:
    """Find a section by header regex. Returns (start, content_start) or None."""
    m = re.search(header_re, body, re.MULTILINE)
    if m:
        return m.start(), m.end()
    return None


def _get_section_header(subdomain: str) -> str:
    """Get the appropriate section header for this subdomain."""
    if subdomain == "blog.aspose.org":
        return RELATED_RESOURCES_HEADER
    return SEE_ALSO_HEADER


def backfill_markdown(
    file_path: Path,
    target_url: str,
    family: str,
    platform: str | None,
    subdomain: str,
    page_type: str,
    families_map: dict,
    platforms_map: dict,
    *,
    dry_run: bool = True,
    target_type: str | None = None,
) -> BackfillChange:
    """Insert backlink into a Markdown page (docs/kb/reference/blog).

    target_type: "platform" or "family" — controls anchor text generation.
    """
    rel = file_path.relative_to(_REPO_ROOT).as_posix()
    raw = file_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(raw)

    # Idempotency: check if target URL already in body
    if target_url.rstrip("/") in body:
        return BackfillChange(
            file=rel, subdomain=subdomain, family=family, platform=platform,
            page_type=page_type, target_url=target_url,
            action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
            before_snippet=body[:200], after_snippet=body[:200],
            skipped=True, skip_reason="Already contains target URL (idempotent)", dry_run=dry_run,
        )

    # Max-link guard
    link_count, _ = count_qualifying_com_links(body)
    if link_count >= MAX_QUALIFYING_LINKS:
        return BackfillChange(
            file=rel, subdomain=subdomain, family=family, platform=platform,
            page_type=page_type, target_url=target_url,
            action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
            before_snippet=body[:200], after_snippet="",
            skipped=True, skip_reason=f"Already at max links ({link_count})", dry_run=dry_run,
        )

    section_header = _get_section_header(subdomain)
    entry = _build_see_also_entry(target_url, family, platform, subdomain, families_map, platforms_map,
                                   target_type=target_type)

    # Build the new body
    new_body = _insert_see_also(body, section_header, entry, subdomain)

    if not dry_run:
        new_raw = fm + new_body
        file_path.write_text(new_raw, encoding="utf-8")

    return BackfillChange(
        file=rel, subdomain=subdomain, family=family, platform=platform,
        page_type=page_type, target_url=target_url,
        action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
        before_snippet=body[:200], after_snippet=new_body[:200],
        dry_run=dry_run,
    )


def _insert_see_also(body: str, section_header: str, entry: str, subdomain: str) -> str:
    """Insert or append to See Also / Related Resources section."""
    # Check if section already exists
    header_pattern = rf"^{re.escape(section_header)}\s*$"
    existing = _find_section(body, header_pattern)

    if existing:
        # Append to existing section
        section_start, content_start = existing
        # Find end of section (next ## heading or end of file)
        next_heading = re.search(r'^\s*##', body[content_start:], re.MULTILINE)
        if next_heading:
            insert_at = content_start + next_heading.start()
            return body[:insert_at].rstrip() + "\n" + entry + "\n\n" + body[insert_at:]
        else:
            # Append at end of section
            return body.rstrip() + "\n" + entry + "\n"
    else:
        # Create new section at end of body
        # Make sure we're not inside a code fence
        body_stripped = body.rstrip()

        # Close any unterminated code fence (safety guard)
        fence_count = len(re.findall(r'```', body_stripped))
        if fence_count % 2 == 1:
            body_stripped += "\n```"

        return body_stripped + f"\n\n{section_header}\n\n{entry}\n"


# ──────────────────────────────────────────────────────────────────────────────
# Main backfill runner
# ──────────────────────────────────────────────────────────────────────────────

SUBDOMAIN_ROOTS = {
    "docs.aspose.org":      "content/docs.aspose.org/en",
    "kb.aspose.org":        "content/kb.aspose.org/en",
    "reference.aspose.org": "content/reference.aspose.org/en",
    "products.aspose.org":  "content/products.aspose.org/en",
    "blog.aspose.org":      "content/blog.aspose.org",
}

OUT_OF_SCOPE_TYPES = {
    PageType.PRODUCTS_ROOT, PageType.BLOG_ARCHIVE, PageType.BLOG_UTILITY,
    PageType.SUBDOMAIN_ROOT, PageType.LOCALE_FILE, PageType.LOCALE_DIR,
    PageType.UNKNOWN_PATTERN,
}


def _load_display_maps(repo_root: Path) -> tuple[dict, dict]:
    """Load families and platforms display name maps."""
    try:
        families_map = json.loads((repo_root / "data" / "families.json").read_text(encoding="utf-8"))
    except Exception:
        families_map = {}

    try:
        import yaml as _yaml
        taxonomy = _yaml.safe_load(
            (repo_root / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml")
            .read_text(encoding="utf-8")
        )
        raw_plats = taxonomy.get("platforms") or {}
        platforms_map = {
            k: (v if isinstance(v, str) else v.get("display_name", k.title()))
            for k, v in raw_plats.items()
        }
    except Exception:
        platforms_map = {}

    return families_map, platforms_map


def run_backfill(
    repo_root: Path,
    target_map: dict,
    *,
    subdomains: list[str] | None = None,
    family_filter: str | None = None,
    platform_filter: str | None = None,
    dry_run: bool = True,
    include_protected: bool = False,
) -> BackfillManifest:
    """Run backfill across all matching content. Returns a BackfillManifest."""
    ts = datetime.now(timezone.utc).isoformat()
    families_map, platforms_map = _load_display_maps(repo_root)
    target_subdomains = subdomains or list(SUBDOMAIN_ROOTS.keys())

    changes: list[BackfillChange] = []
    errors: list[dict] = []
    candidates = 0

    for sd in target_subdomains:
        if sd not in SUBDOMAIN_ROOTS:
            continue
        root = repo_root / SUBDOMAIN_ROOTS[sd]
        if not root.exists():
            print(f"  WARN: Content root not found: {root}", file=sys.stderr)
            continue

        for fpath in sorted(root.rglob("*.md")):
            # Family/platform filter
            if family_filter or platform_filter:
                rel = fpath.relative_to(root).as_posix()
                parts = rel.split("/")
                if family_filter and (len(parts) < 1 or parts[0] != family_filter):
                    continue
                if platform_filter and (len(parts) < 2 or parts[1] != platform_filter):
                    continue

            candidates += 1

            try:
                pt, family, platform, subdomain = classify_page_type(fpath, repo_root)
            except Exception as exc:
                errors.append({"file": str(fpath), "error": f"classify: {exc}"})
                continue

            if pt in OUT_OF_SCOPE_TYPES:
                continue

            # Check auto_updatable (skip protected pages unless --include-protected)
            if not include_protected and sd != "blog.aspose.org":
                try:
                    raw = fpath.read_text(encoding="utf-8")
                    if "auto_updatable: false" in raw:
                        changes.append(BackfillChange(
                            file=fpath.relative_to(repo_root).as_posix(),
                            subdomain=sd, family=family, platform=platform,
                            page_type=pt.value, target_url="",
                            action="skip", before_snippet="", after_snippet="",
                            skipped=True, skip_reason="auto_updatable: false (use --include-protected)",
                            dry_run=dry_run,
                        ))
                        continue
                except Exception:
                    pass

            # Resolve target
            chosen_url, chosen_type, chosen_sd, fallback_reason = resolve_backlink(
                family=family or "",
                platform=platform,
                source_subdomain=sd,
                target_map=target_map,
            )
            if not chosen_url:
                changes.append(BackfillChange(
                    file=fpath.relative_to(repo_root).as_posix(),
                    subdomain=sd, family=family, platform=platform,
                    page_type=pt.value, target_url="",
                    action="skip", before_snippet="", after_snippet="",
                    skipped=True, skip_reason=f"BLOCKED_TARGET: {fallback_reason}",
                    dry_run=dry_run,
                ))
                continue

            # Check existing link count
            try:
                if sd == "products.aspose.org":
                    raw_text = fpath.read_text(encoding="utf-8")
                    fm_text = raw_text
                    if raw_text.startswith("---"):
                        end = raw_text.find("---", 3)
                        if end != -1:
                            fm_text = raw_text[3:end]
                    import yaml as _yaml
                    data = _yaml.safe_load(fm_text)
                    overview_content = (data.get("overview", {}) or {}).get("content", "") or ""
                    link_count, _ = count_qualifying_com_links(overview_content)
                else:
                    raw_text = fpath.read_text(encoding="utf-8")
                    _, body = _split_frontmatter(raw_text)
                    link_count, _ = count_qualifying_com_links(body)
            except Exception:
                link_count = 0

            if link_count > 0:
                # Page already has aspose.com links — check compliance:
                # If links are in the acceptable fallback chain → COMPLIANT, skip.
                # If links are WRONG_TARGET and count < MAX → add correct link.
                # If OVER_LIMIT (>= MAX) → skip without touching.
                if link_count >= MAX_QUALIFYING_LINKS:
                    changes.append(BackfillChange(
                        file=fpath.relative_to(repo_root).as_posix(),
                        subdomain=sd, family=family, platform=platform,
                        page_type=pt.value, target_url=chosen_url,
                        action="skip", before_snippet="", after_snippet="",
                        skipped=True, skip_reason=f"Has {link_count} existing aspose.com link(s) >= max {MAX_QUALIFYING_LINKS}",
                        dry_run=dry_run,
                    ))
                    continue
                # link_count == 1: check if it already matches acceptable chain
                try:
                    if sd == "products.aspose.org":
                        raw_text2 = fpath.read_text(encoding="utf-8")
                        fm_text2 = raw_text2
                        if raw_text2.startswith("---"):
                            end2 = raw_text2.find("---", 3)
                            if end2 != -1:
                                fm_text2 = raw_text2[3:end2]
                        import yaml as _yaml2
                        data2 = _yaml2.safe_load(fm_text2)
                        ov2 = (data2.get("overview", {}) or {}).get("content", "") or ""
                        _, existing_urls = count_qualifying_com_links(ov2)
                    else:
                        raw_text2 = fpath.read_text(encoding="utf-8")
                        _, body2 = _split_frontmatter(raw_text2)
                        _, existing_urls = count_qualifying_com_links(body2)
                except Exception:
                    existing_urls = []
                compliance = classify_compliance(
                    link_count, existing_urls, chosen_url,
                    family=family, platform=platform,
                )
                if compliance == COMPLIANT:
                    changes.append(BackfillChange(
                        file=fpath.relative_to(repo_root).as_posix(),
                        subdomain=sd, family=family, platform=platform,
                        page_type=pt.value, target_url=chosen_url,
                        action="skip", before_snippet="", after_snippet="",
                        skipped=True, skip_reason="Already COMPLIANT",
                        dry_run=dry_run,
                    ))
                    continue
                # WRONG_TARGET with room to add — fall through to backfill

            # Apply backfill
            try:
                if sd == "products.aspose.org":
                    change = backfill_products_yaml(
                        fpath, chosen_url, family or "", platform,
                        families_map, platforms_map, dry_run=dry_run,
                        target_type=chosen_type,
                    )
                else:
                    change = backfill_markdown(
                        fpath, chosen_url, family or "", platform,
                        sd, pt.value, families_map, platforms_map, dry_run=dry_run,
                        target_type=chosen_type,
                    )
                changes.append(change)
            except Exception as exc:
                rel = fpath.relative_to(repo_root).as_posix()
                errors.append({"file": rel, "error": str(exc)})

    # Build manifest
    modified = sum(1 for c in changes if not c.skipped)
    skipped = sum(1 for c in changes if c.skipped)

    manifest = BackfillManifest(
        generated_at=ts,
        generator=f"backlink_backfill.py v{SCRIPT_VERSION}",
        dry_run=dry_run,
        total_candidates=candidates,
        total_modified=modified,
        total_skipped=skipped,
        total_errors=len(errors),
        changes=[asdict(c) for c in changes],
        errors=errors,
        rollback_commands=[
            f"git checkout HEAD -- {c.file}"
            for c in changes if not c.skipped and not dry_run
        ],
    )
    return manifest


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backlink insertion engine for aspose.org English content."
    )
    parser.add_argument("--write", action="store_true",
                        help="Apply writes (default is dry-run)")
    parser.add_argument("--subdomain", nargs="+", choices=list(SUBDOMAIN_ROOTS.keys()),
                        help="Restrict to specific subdomain(s)")
    parser.add_argument("--family", help="Restrict to a specific family")
    parser.add_argument("--platform", help="Restrict to a specific platform")
    parser.add_argument("--include-protected", action="store_true",
                        help="Include auto_updatable: false pages")
    parser.add_argument("--output",
                        help="Output manifest JSON path (default: reports/backlinks/backfill_...)")
    parser.add_argument("--target-map", help="Path to data/aspose_com_targets.json")
    args = parser.parse_args()

    repo_root = _REPO_ROOT
    dry_run = not args.write
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # Load target map
    print(f"Loading target map...", file=sys.stderr)
    try:
        if args.target_map:
            target_map = json.loads(Path(args.target_map).read_text(encoding="utf-8"))
        else:
            target_map = load_target_map(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FATAL: Cannot load target map — {exc}", file=sys.stderr)
        return 1

    mode = "DRY-RUN" if dry_run else "WRITE"
    print(f"Running backfill [{mode}]...", file=sys.stderr)

    manifest = run_backfill(
        repo_root=repo_root,
        target_map=target_map,
        subdomains=args.subdomain,
        family_filter=args.family,
        platform_filter=args.platform,
        dry_run=dry_run,
        include_protected=args.include_protected,
    )

    # Write manifest
    reports_dir = repo_root / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)

    prefix = "backfill_dry_run" if dry_run else "backfill_write"
    if args.output:
        json_out = Path(args.output)
    else:
        json_out = reports_dir / f"{prefix}_{ts}.json"

    json_out.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Write rollback script (write mode only)
    if not dry_run and manifest.rollback_commands:
        rollback_path = reports_dir / f"backfill_rollback_{ts}.sh"
        rollback_path.write_text(
            "#!/bin/bash\n# Auto-generated rollback script\n" +
            "\n".join(manifest.rollback_commands) + "\n",
            encoding="utf-8",
        )
        print(f"  Rollback: {rollback_path}", file=sys.stderr)

    # Console summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Backfill [{mode}] Complete", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Candidates: {manifest.total_candidates}", file=sys.stderr)
    print(f"  Modified:   {manifest.total_modified}", file=sys.stderr)
    print(f"  Skipped:    {manifest.total_skipped}", file=sys.stderr)
    print(f"  Errors:     {manifest.total_errors}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Manifest: {json_out}", file=sys.stderr)

    if manifest.errors:
        print(f"\nErrors:", file=sys.stderr)
        for err in manifest.errors:
            print(f"  [{err.get('file', '?')}] {err.get('error', '')}", file=sys.stderr)

    # Show sample of what would be written (dry-run preview)
    if dry_run:
        modified_changes = [c for c in manifest.changes if not c.get("skipped")]
        shown = 0
        for change in modified_changes[:5]:
            if shown == 0:
                print(f"\nSample diffs (first {min(5, len(modified_changes))}):", file=sys.stderr)
            print(f"\n  [{change['action']}] {change['file']}", file=sys.stderr)
            print(f"    Target: {change['target_url']}", file=sys.stderr)
            after = change.get("after_snippet", "")
            if after:
                print(f"    After:  ...{after[-100:]}", file=sys.stderr)
            shown += 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
