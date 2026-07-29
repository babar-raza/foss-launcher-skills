"""
feature_list_extender.py — TC-07: Extend feature-list pages with new high-importance APIs.

Handles new_apis and new_claims (class_importance >= 0.7) from knowledge_delta.json.
Uses an LLM to draft a new bullet, grounded with claim text + 3 neighbouring bullets.
Runs naturalness_check.py before inserting; attach_evidence.py after write.

Only operates on English content. Locale-suffixed files are skipped.

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.feature_list_extender \\
        3d net --dry-run
    PYTHONPATH=scripts/pipeline python -m commands.content.feature_list_extender \\
        3d net --execute
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

# ── Globals / configure() seam ─────────────────────────────────────────────

_cfg_repo_root: Path | None = None
_cfg_llm_router_class: Any = None


def configure(
    *,
    repo_root: Path | None = None,
    llm_router_class: Any = None,
) -> None:
    """Override defaults (used by tests for isolation)."""
    global _cfg_repo_root, _cfg_llm_router_class
    _cfg_repo_root = repo_root
    _cfg_llm_router_class = llm_router_class


def _get_repo_root() -> Path:
    if _cfg_repo_root is not None:
        return _cfg_repo_root
    return Path(__file__).resolve().parents[3]


# ── Constants ──────────────────────────────────────────────────────────────

# Only extend feature lists for classes with importance >= this threshold
_IMPORTANCE_THRESHOLD = 0.7

# Result codes
R_EXTENDED = "FEATURE_LIST_EXTENDED"
R_NOOP = "NOOP"
R_SKIPPED_LOCALE = "SKIPPED_LOCALE"
R_SKIPPED_NO_CHANGE = "SKIPPED_NO_CHANGE"
R_NO_DELTA = "NO_KNOWLEDGE_DELTA"
R_DRY_RUN = "DRY_RUN"


# ── Importance computation (mirrors knowledge_core.py) ─────────────────────

def _compute_class_importance(entry: dict) -> float:
    """Compute class importance score from coverage_matrix.json entry."""
    mc = entry.get("method_count", 0)
    pc = entry.get("property_count", 0)
    base = min(1.0, (mc + pc) / 20)
    if entry.get("has_tests"):
        base += 0.15
    if entry.get("has_doc"):
        base += 0.1
    if mc <= 1 and pc == 0:
        base -= 0.2
    return max(0.0, min(1.0, base))


def _load_coverage_importance(family: str, platform: str, root: Path) -> dict[str, float]:
    """Return {class_name: importance_score} for the product."""
    path = root / "knowledge" / family / platform / "merged" / "coverage_matrix.json"
    if not path.exists():
        return {}
    try:
        matrix = json.loads(path.read_text(encoding="utf-8"))
        return {
            e["class"]: _compute_class_importance(e)
            for e in matrix
            if isinstance(e, dict) and e.get("class")
        }
    except (json.JSONDecodeError, OSError):
        return {}


# ── Locale guard ────────────────────────────────────────────────────────────

def _is_english_path(path: Path) -> bool:
    """Return True if the path is English content (not locale-suffixed or locale-dir)."""
    # Blog: reject index.fr.md, index.de.md, etc.
    stem = path.stem
    if re.search(r'\.[a-z]{2}$', stem):
        return False
    # Docs/KB/Reference: require /en/ in path
    parts = path.parts
    content_idx = next((i for i, p in enumerate(parts) if p == "content"), -1)
    if content_idx >= 0:
        remaining = parts[content_idx + 1:]
        # blog.aspose.org paths don't use /en/
        if remaining and "blog.aspose.org" in remaining[0]:
            return True
        # Other sites require /en/ in path
        return "en" in remaining
    return True


# ── Feature-list page finder ────────────────────────────────────────────────

_FEATURE_LIST_KEYWORDS = frozenset([
    "features", "capabilities", "key-features", "what-you-can-do",
])


def _find_feature_list_pages(family: str, platform: str, root: Path) -> list[Path]:
    """
    Return English content pages that are likely feature-list pages.
    Uses content_region_index if available; falls back to slug heuristics.
    """
    # Try region index first
    index_path = root / "reports" / "content_region_index" / family / f"{platform}.json"
    if index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
            pages = []
            for rel in idx.get("feature_list_pages", []):
                p = root / rel
                if p.exists() and _is_english_path(p):
                    pages.append(p)
            if pages:
                return pages
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: scan English content directories
    pages: list[Path] = []
    for site_dir in [
        root / "content" / "docs.aspose.org" / "en" / family / platform,
        root / "content" / "kb.aspose.org" / "en" / family / platform,
    ]:
        if not site_dir.exists():
            continue
        for md_file in site_dir.rglob("*.md"):
            if not _is_english_path(md_file):
                continue
            slug = md_file.stem.lower()
            if any(kw in slug for kw in _FEATURE_LIST_KEYWORDS):
                pages.append(md_file)
    return pages


# ── Bullet extraction helpers ───────────────────────────────────────────────

_BULLET_RE = re.compile(r'^(\s*[-*+]\s)', re.MULTILINE)


def _extract_neighbouring_bullets(content: str, position: int, n: int = 3) -> list[str]:
    """Return up to n bullets nearest to position in content."""
    bullets = []
    for m in _BULLET_RE.finditer(content):
        line_start = m.start()
        line_end = content.find('\n', line_start)
        line = content[line_start:line_end if line_end >= 0 else len(content)]
        bullets.append((line_start, line.strip()))

    if not bullets:
        return []

    # Sort by distance to position
    bullets.sort(key=lambda b: abs(b[0] - position))
    return [b[1] for b in bullets[:n]]


def _find_first_bullet_position(content: str) -> int:
    """Return index of the first bullet line, or end of content."""
    m = _BULLET_RE.search(content)
    return m.start() if m else len(content)


# ── LLM bullet generation ──────────────────────────────────────────────────

def _generate_bullet(
    api_name: str,
    claim_text: str,
    neighbouring_bullets: list[str],
    family: str,
    platform: str,
) -> str | None:
    """Call LLM to draft a new feature-list bullet. Returns None on failure."""
    router_class = _cfg_llm_router_class
    if router_class is None:
        try:
            from commands.ops.llm_router import LLMRouter
            router_class = LLMRouter
        except ImportError:
            return None

    neighbours_block = "\n".join(f"  {b}" for b in neighbouring_bullets) or "  (none)"
    system_prompt = (
        f"You are a technical writer maintaining {family}/{platform} documentation. "
        f"Add exactly ONE new bullet point to a feature-list page. "
        f"Match the tone and length of the neighbouring bullets. "
        f"Do not introduce any capability that is not explicitly stated in the claim below. "
        f"If you are uncertain, write a conservative, factual bullet. "
        f"Output only the bullet line, starting with '- '."
    )
    user_prompt = (
        f"New API: {api_name}\n"
        f"Claim: {claim_text}\n\n"
        f"Neighbouring bullets for tone reference:\n{neighbours_block}\n\n"
        f"New bullet:"
    )

    try:
        router = router_class()
        from commands.ops.llm_router import LLMCallContext
        result = router.call_chat(
            prompt_system=system_prompt,
            prompt_user=user_prompt,
            temperature=0.1,
            json_extract=False,
            context=LLMCallContext.create("feature-list-extender", "content-enrichment", "features"),
        )
        if result and result.data and isinstance(result.data, str):
            bullet = result.data.strip()
            # Ensure it starts with a bullet marker
            if not _BULLET_RE.match(bullet):
                bullet = f"- {bullet}"
            return bullet
    except Exception:
        pass
    return None


# ── Core extension logic ────────────────────────────────────────────────────

def _get_claim_text(
    api_name: str,
    family: str,
    platform: str,
    root: Path,
) -> str:
    """Return the first claim text for api_name, or a generic fallback."""
    claims_path = root / "knowledge" / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return f"Supports {api_name} operations."
    try:
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
        if isinstance(claims, dict):
            claims = claims.get("claims", [])
        for c in claims:
            if not isinstance(c, dict):
                continue
            sym = c.get("api_member") or c.get("symbol") or ""
            if sym == api_name or api_name in sym:
                return c.get("claim_text") or c.get("text") or f"Supports {api_name}."
    except (json.JSONDecodeError, OSError):
        pass
    return f"Supports {api_name}."


def extend_feature_page(
    page_path: Path,
    api_name: str,
    claim_text: str,
    family: str,
    platform: str,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Insert one bullet for api_name into a feature-list page."""
    if not _is_english_path(page_path):
        return {"result": R_SKIPPED_LOCALE, "page": str(page_path), "api": api_name}

    content = page_path.read_text(encoding="utf-8")

    # Skip if api_name already mentioned (idempotency)
    if api_name in content:
        return {"result": R_SKIPPED_NO_CHANGE, "page": str(page_path), "api": api_name}

    # Find insertion point (end of first bullet group)
    first_bullet_pos = _find_first_bullet_position(content)
    neighbours = _extract_neighbouring_bullets(content, first_bullet_pos, n=3)

    bullet = _generate_bullet(api_name, claim_text, neighbours, family, platform)
    if not bullet:
        # Deterministic fallback
        bullet = f"- `{api_name}`: {claim_text}"

    # Naturalness check
    neighbours_text = "\n".join(neighbours)
    from commands.ops.naturalness_check import check as naturalness_check
    nat_result = naturalness_check(original=neighbours_text, generated=bullet)
    warnings = nat_result.findings[:]

    if dry_run:
        return {
            "result": R_DRY_RUN,
            "page": str(page_path),
            "api": api_name,
            "bullet": bullet,
            "naturalness": nat_result.verdict,
            "naturalness_warnings": warnings,
        }

    # Insert bullet at the end of the first bullet group
    # Find last consecutive bullet line starting from first_bullet_pos
    lines = content.splitlines(keepends=True)
    insert_line = 0
    in_bullets = False
    for i, line in enumerate(lines):
        if _BULLET_RE.match(line):
            in_bullets = True
            insert_line = i + 1
        elif in_bullets and line.strip():
            break  # end of bullet group

    if insert_line == 0:
        # No bullets found, append before the last section
        updated = content.rstrip() + f"\n\n{bullet}\n"
    else:
        lines.insert(insert_line, bullet + "\n")
        updated = "".join(lines)

    page_path.write_text(updated, encoding="utf-8")

    # Re-attach evidence
    try:
        attach_script = _get_repo_root() / "scripts" / "pipeline" / "commands" / "ops" / "attach_evidence.py"
        if attach_script.exists():
            subprocess.run(
                [sys.executable, str(attach_script), "--files", str(page_path)],
                check=False,
                capture_output=True,
            )
    except OSError:
        pass

    return {
        "result": R_EXTENDED,
        "page": str(page_path),
        "api": api_name,
        "bullet": bullet,
        "naturalness": nat_result.verdict,
        "naturalness_warnings": warnings,
    }


# ── Orchestrator ────────────────────────────────────────────────────────────

def run_extension(
    family: str,
    platform: str,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Find high-importance new APIs from knowledge_delta.json, extend feature-list pages.
    """
    root = _get_repo_root()
    delta_path = root / "knowledge" / family / platform / "merged" / "knowledge_delta.json"
    if not delta_path.exists():
        return {"files_checked": 0, "files_extended": 0, "changes": [
            {"error": R_NO_DELTA}
        ]}

    try:
        delta = json.loads(delta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"files_checked": 0, "files_extended": 0, "changes": [
            {"error": "DELTA_PARSE_ERROR"}
        ]}

    new_apis: list[str] = delta.get("new_apis", [])
    if not new_apis:
        return {"files_checked": 0, "files_extended": 0, "changes": []}

    # Filter by importance threshold
    importance_map = _load_coverage_importance(family, platform, root)
    high_importance = [
        a for a in new_apis
        if importance_map.get(a, 0.5) >= _IMPORTANCE_THRESHOLD
    ]
    if not high_importance:
        return {"files_checked": 0, "files_extended": 0, "changes": []}

    # Find feature-list pages
    feature_pages = _find_feature_list_pages(family, platform, root)
    if not feature_pages:
        return {"files_checked": 0, "files_extended": 0, "changes": [
            {"warning": "NO_FEATURE_LIST_PAGES"}
        ]}

    changes: list[dict] = []
    files_extended = 0

    for api_name in high_importance:
        claim_text = _get_claim_text(api_name, family, platform, root)
        for page in feature_pages:
            result = extend_feature_page(
                page, api_name, claim_text, family, platform, dry_run=dry_run
            )
            changes.append(result)
            if result["result"] == R_EXTENDED:
                files_extended += 1

    return {
        "files_checked": len(feature_pages),
        "files_extended": files_extended,
        "high_importance_apis": high_importance,
        "changes": changes,
    }


# ── CLI ────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="feature_list_extender — extend feature lists with new high-importance APIs."
    )
    p.add_argument("family", help="Product family (e.g. 3d)")
    p.add_argument("platform", help="Platform (e.g. net)")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Preview changes without writing (default).")
    p.add_argument("--execute", dest="dry_run", action="store_false",
                   help="Write changes to disk.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = run_extension(args.family, args.platform, dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "EXECUTE"
    print(f"[feature_list_extender] {mode} {args.family}/{args.platform}")
    print(f"  files_checked:  {summary['files_checked']}")
    print(f"  files_extended: {summary['files_extended']}")
    for c in summary.get("changes", []):
        r = c.get("result") or c.get("error") or c.get("warning", "")
        api = c.get("api", "")
        page = Path(c.get("page", "")).name if c.get("page") else ""
        if r not in (R_NOOP, R_SKIPPED_NO_CHANGE):
            print(f"  {r:30s} {api:40s} {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
