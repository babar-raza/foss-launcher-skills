"""check_stale_refresh_gate.py — HARDEN-A8: pre-commit stale-refresh gate.

Blocks a commit that stages a SPECIFIC page triage_confirm.py (S-92) most
recently flagged as stale, unless the staged content is a fresh rewrite of
that exact page (hash no longer matches what triage flagged) or a governed
override token covers it. This makes refresh-product.md's long-standing claim
that "S-76 is gated on triage verdict" actually true — before A8, nothing on
the commit path read the verdict at all.

R1 correction (per adversarial review, 2026-07-22): the first version of this
gate blocked on the {family, platform} PAIR's aggregate stale_count/error_count
— which meant any commit touching ANY file under a product with pre-existing
stale pages (4 real products in this repo already have nonzero stale counts
from prior sprints: 3d/java, 3d/net, cells/java, pdf/net) was hard-blocked
forever, with no override, even for changes wholly unrelated to the stale
pages. Scoped instead to the PER-FILE verdict (triage_confirm's `results` list
already carries `page_path`/`stale` per page) plus a governed override escape
hatch, matching the design already proven safe in Step 21.

Semantics (deterministic):
  - No verdict file for the pair                 -> PASS (no refresh cycle on record)
  - Staged file not present in the verdict's
    `results` list (never checked, e.g. new page) -> PASS (nothing on record for it)
  - Staged file present with stale=False and
    verdict != "read_error"                       -> PASS
  - Staged file present with stale=True, or
    verdict == "read_error"                       -> BLOCK (unless a pending
                                                      override token covers it)

Usage: staged content paths on stdin (one per line), exit 0 pass / 1 block.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# content/{site}/en/{family}/{platform}/...  (docs, kb, products, reference)
_EN_RE = re.compile(
    r"^content/(?:docs|kb|products|reference)\.aspose\.org/en/([a-z0-9-]+)/([a-z0-9-]+)/"
)
# content/blog.aspose.org/{family}/{platform}/...  (blog has no /en/)
_BLOG_RE = re.compile(r"^content/blog\.aspose\.org/([a-z0-9-]+)/([a-z0-9-]+)/")


def pairs_from_paths(paths: list[str]) -> dict[tuple[str, str], list[str]]:
    """Map each (family, platform) pair to the staged paths under it."""
    pairs: dict[tuple[str, str], list[str]] = {}
    for raw in paths:
        p = raw.replace("\\", "/").strip()
        m = _EN_RE.match(p) or _BLOG_RE.match(p)
        if m:
            pairs.setdefault((m.group(1), m.group(2)), []).append(p)
    return pairs


def _normalize_verdict_path(raw: str) -> str:
    """triage_confirm.py stores page_path as given at scan time (often absolute
    or repo-relative with OS separators) — normalize both sides the same way
    so comparison is reliable regardless of how each was produced."""
    p = raw.replace("\\", "/")
    try:
        rel = Path(p).resolve().relative_to(_REPO_ROOT.resolve())
        return str(rel).replace("\\", "/")
    except (ValueError, OSError):
        # Already relative (or outside repo root, e.g. a test fixture) — use as-is,
        # stripping a leading repo-root-like prefix if one slipped through.
        return p.split(_REPO_ROOT.name + "/", 1)[-1] if _REPO_ROOT.name in p else p


def _has_override(path: str) -> bool:
    """Governed override check (same mechanism as Step 21 — no new bypass channel)."""
    script = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "governance" / "override_manager.py"
    if not script.is_file():
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script), "validate-for-path", path],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check_pair(family: str, platform: str, staged_paths: list[str],
               repo_root: Path = _REPO_ROOT) -> list[tuple[str, str]]:
    """Return [(staged_path, reason)] for staged files this pair's triage
    verdict flags as stale/unreadable and that lack a governed override."""
    verdict_path = repo_root / "reports" / "refresh_review" / family / platform / "triage_verdict.yaml"
    if not verdict_path.is_file():
        return []
    try:
        import yaml
        data = yaml.safe_load(verdict_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # unreadable verdict = unverifiable = block every staged file
        return [(p, f"triage_verdict.yaml unreadable ({exc}) — re-run triage_confirm")
                for p in staged_paths]

    flagged: dict[str, str] = {}
    for entry in data.get("results", []):
        if not isinstance(entry, dict):
            continue
        norm = _normalize_verdict_path(str(entry.get("page_path", "")))
        if entry.get("verdict") == "read_error":
            flagged[norm] = f"triage read error: {'; '.join(entry.get('reasons', []))}"
        elif entry.get("stale"):
            flagged[norm] = f"triage flagged stale: {'; '.join(entry.get('reasons', []))}"

    blocked: list[tuple[str, str]] = []
    for staged in staged_paths:
        norm = _normalize_verdict_path(staged)
        reason = flagged.get(norm)
        if reason is None:
            continue
        if _has_override(staged):
            continue
        blocked.append((staged, reason))
    return blocked


def main() -> int:
    staged = [line.strip() for line in sys.stdin if line.strip()]
    if not staged:
        return 0
    pairs = pairs_from_paths(staged)
    if not pairs:
        return 0

    all_blocked: list[tuple[str, str]] = []
    for (family, platform), paths in sorted(pairs.items()):
        # Pass _REPO_ROOT explicitly (module global read at call time, not the
        # function's bind-time default) so a test's monkeypatch of _REPO_ROOT
        # actually takes effect.
        all_blocked.extend(check_pair(family, platform, paths, repo_root=_REPO_ROOT))

    if all_blocked:
        print(f"BLOCKED: {len(all_blocked)} staged page(s) flagged stale by the "
              f"most recent triage_confirm run:", file=sys.stderr)
        for path, reason in all_blocked:
            print(f"  {path}: {reason}", file=sys.stderr)
        print("Fix: rewrite the page's body prose to match current knowledge, then "
              "re-run triage_confirm to clear the flag — or create a governed "
              "override: override_manager.py create --paths <file> --reason '...' "
              "--plan '<plan>'", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
