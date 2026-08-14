"""knowledge_git_migration.py — classify and (bounded) apply git-tracking for knowledge/.

CONTRACT: scripts/pipeline/commands/ops/knowledge_git_migration.py
  purpose: knowledge/ was entirely gitignored, which removed any durable, diffable,
           cross-session record of generated facts (model.yaml, api_surface.json,
           formats.md, claims.json) — the structural root cause of the cells/net
           stale-facts incident (FRESH-001, 2026-08-14). This script applies the
           declarative classification in config/knowledge_tracking_policy.yaml to
           every product directory under knowledge/, reporting what would newly
           become git-tracked and what stays local/gitignored.
  safety:  NEVER deletes anything. A DROP classification leaves the file exactly
           where it is on disk (already gitignored today, so this is a strict
           no-op for DROP items). Default mode is dry-run (report only). --apply
           only stages (`git add`) KEEP-classified files for explicitly named
           products — never commits, never pushes, never touches unnamed products.
  fail-closed: any file under a product directory that matches neither a
           keep_patterns nor a drop_patterns glob is reported as UNCLASSIFIED and
           left completely untouched (not tracked, not deleted, not reported as
           either safe or unsafe — surfaced for a human/agent to classify).

Usage:
    python scripts/pipeline/commands/ops/knowledge_git_migration.py audit
    python scripts/pipeline/commands/ops/knowledge_git_migration.py audit --json
    python scripts/pipeline/commands/ops/knowledge_git_migration.py apply --products cells/net
    python scripts/pipeline/commands/ops/knowledge_git_migration.py apply --products cells/net,cells/go
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import yaml  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
PRODUCTS_JSON = REPO_ROOT / "data" / "products.json"
POLICY_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "knowledge_tracking_policy.yaml"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, KNOWLEDGE_ROOT, PRODUCTS_JSON, POLICY_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    PRODUCTS_JSON = REPO_ROOT / "data" / "products.json"
    POLICY_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "knowledge_tracking_policy.yaml"


def load_policy() -> dict:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


def _load_products() -> list[dict]:
    if not PRODUCTS_JSON.is_file():
        return []
    try:
        return json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def classify_file(rel_path: str, policy: dict) -> str:
    """Classify one file path (relative to knowledge/{family}/{platform}/) as
    KEEP, DROP, or UNCLASSIFIED against the policy's glob patterns.

    KEEP is checked first: a file matching both would be a policy authoring
    error, and KEEP (git-tracked) is the more consequential/visible outcome,
    so it wins rather than being silently shadowed by DROP.
    """
    rel_posix = rel_path.replace("\\", "/")
    for pattern in policy.get("keep_patterns", []):
        if fnmatch.fnmatch(rel_posix, pattern):
            return "KEEP"
    for pattern in policy.get("drop_patterns", []):
        if fnmatch.fnmatch(rel_posix, pattern):
            return "DROP"
    return "UNCLASSIFIED"


def classify_product(family: str, platform: str, policy: dict) -> dict:
    """Walk knowledge/{family}/{platform}/ and classify every file in it.

    Returns a dict with keep/drop/unclassified file lists (paths relative to the
    product dir) and byte totals for each bucket.
    """
    product_dir = KNOWLEDGE_ROOT / family / platform
    result = {
        "family": family,
        "platform": platform,
        "exists": product_dir.is_dir(),
        "keep": [], "keep_bytes": 0,
        "drop": [], "drop_bytes": 0,
        "unclassified": [], "unclassified_bytes": 0,
    }
    if not product_dir.is_dir():
        return result

    for path in sorted(product_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(product_dir)).replace("\\", "/")
        verdict = classify_file(rel, policy)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if verdict == "KEEP":
            result["keep"].append(rel)
            result["keep_bytes"] += size
        elif verdict == "DROP":
            result["drop"].append(rel)
            result["drop_bytes"] += size
        else:
            result["unclassified"].append(rel)
            result["unclassified_bytes"] += size
    return result


def _excluded_top_level(policy: dict) -> set[str]:
    return set(policy.get("excluded_top_level_dirs", []))


def discover_products() -> list[tuple[str, str]]:
    """Return (family, platform) pairs from data/products.json that have a local
    knowledge/{family}/{platform}/ directory on disk."""
    pairs = []
    for entry in _load_products():
        family, platform = entry.get("family"), entry.get("platform")
        if not family or not platform:
            continue
        if (KNOWLEDGE_ROOT / family / platform).is_dir():
            pairs.append((family, platform))
    return pairs


def audit(*, products: "list[tuple[str, str]] | None" = None) -> dict:
    """Dry-run classification across products (default: every product with local
    knowledge/ present). Never touches the filesystem or git."""
    policy = load_policy()
    targets = products if products is not None else discover_products()
    rows = [classify_product(f, p, policy) for f, p in targets]
    totals = {
        "products": len(rows),
        "keep_bytes": sum(r["keep_bytes"] for r in rows),
        "drop_bytes": sum(r["drop_bytes"] for r in rows),
        "unclassified_bytes": sum(r["unclassified_bytes"] for r in rows),
        "unclassified_files": sum(len(r["unclassified"]) for r in rows),
    }
    return {"products": rows, "totals": totals}


def apply(products: "list[tuple[str, str]]") -> dict:
    """Stage (git add) KEEP-classified files for exactly the named products.

    Never commits. Never touches products not explicitly named. Returns a
    per-product report of what was staged.
    """
    policy = load_policy()
    results = []
    for family, platform in products:
        row = classify_product(family, platform, policy)
        product_dir = KNOWLEDGE_ROOT / family / platform
        staged = []
        for rel in row["keep"]:
            fpath = product_dir / rel
            if not fpath.is_file():
                continue
            # Retry-with-backoff on transient failure (observed live 2026-08-14
            # during the T12 pilot: AV/indexer handle contention on a freshly-
            # written snippet file caused a single `git add` attempt to silently
            # not stage it, with no non-zero exit surfaced past the loop -- same
            # class of transient contention promote.py's atomic swap already
            # guards against; this loop previously had no retry at all).
            proc = None
            for attempt in range(5):
                proc = subprocess.run(
                    ["git", "add", "--", str(fpath)],
                    cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
                )
                if proc.returncode == 0:
                    break
                time.sleep(0.2 * (attempt + 1))
            if proc is not None and proc.returncode == 0:
                staged.append(rel)
            else:
                print(f"WARN: git add failed for {fpath}: {proc.stderr.strip() if proc else 'unknown error'}",
                      file=sys.stderr)
        results.append({
            "family": family, "platform": platform,
            "staged_count": len(staged), "staged": staged,
            "unclassified": row["unclassified"],
        })
    return {"applied": results}


def format_report(result: dict) -> str:
    lines = ["# Knowledge Git-Tracking Migration — Audit Report", ""]
    for row in result["products"]:
        lines.append(f"## {row['family']}/{row['platform']}")
        lines.append(
            f"- keep: {len(row['keep'])} files, {row['keep_bytes']:,} bytes"
        )
        lines.append(
            f"- drop (stays gitignored): {len(row['drop'])} files, {row['drop_bytes']:,} bytes"
        )
        if row["unclassified"]:
            lines.append(
                f"- **UNCLASSIFIED (needs policy update): {len(row['unclassified'])} files, "
                f"{row['unclassified_bytes']:,} bytes**"
            )
            for f in row["unclassified"]:
                lines.append(f"  - {f}")
        lines.append("")
    t = result["totals"]
    lines.append("## Totals")
    lines.append(f"- products audited: {t['products']}")
    lines.append(f"- would newly track: {t['keep_bytes']:,} bytes")
    lines.append(f"- stays gitignored: {t['drop_bytes']:,} bytes")
    lines.append(f"- unclassified: {t['unclassified_files']} files, {t['unclassified_bytes']:,} bytes")
    return "\n".join(lines) + "\n"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Classify and apply knowledge/ git-tracking")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="Dry-run classification (default: all discovered products)")
    p_audit.add_argument("--products", default=None,
                          help="Comma-separated family/platform pairs (default: all with local knowledge/)")
    p_audit.add_argument("--json", action="store_true", dest="as_json")
    p_audit.add_argument("--out", default=None, help="Write the markdown report to this path")

    p_apply = sub.add_parser("apply", help="git add KEEP-classified files for named products (no commit)")
    p_apply.add_argument("--products", required=True,
                          help="Comma-separated family/platform pairs, e.g. cells/net,cells/go")

    args = parser.parse_args(argv)

    def _parse_pairs(spec: str) -> list[tuple[str, str]]:
        pairs = []
        for item in spec.split(","):
            item = item.strip()
            if not item:
                continue
            if "/" not in item:
                print(f"ERROR: invalid product spec {item!r}, expected family/platform", file=sys.stderr)
                sys.exit(2)
            f, p = item.split("/", 1)
            pairs.append((f, p))
        return pairs

    if args.command == "audit":
        products = _parse_pairs(args.products) if args.products else None
        result = audit(products=products)
        if args.as_json:
            print(json.dumps(result, indent=2))
        else:
            report = format_report(result)
            print(report)
            if args.out:
                Path(args.out).write_text(report, encoding="utf-8")
        if result["totals"]["unclassified_files"]:
            print(
                f"WARNING: {result['totals']['unclassified_files']} unclassified files found — "
                f"update scripts/pipeline/config/knowledge_tracking_policy.yaml before relying "
                f"on this classification.",
                file=sys.stderr,
            )
            return 1
        return 0

    if args.command == "apply":
        products = _parse_pairs(args.products)
        result = apply(products)
        print(json.dumps(result, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
