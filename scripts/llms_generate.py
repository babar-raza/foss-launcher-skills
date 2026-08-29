"""llms_generate.py -- generate llms-output/ .txt files and per-site llms.txt indexes.

Generalized from aspose.org's S-LG-01 llms-generate skill (2026-08-29 sync).
Iterates config.yaml's sites: block instead of a hardcoded subdomain list --
works against any config.yaml-described Hugo content repo, not just
aspose.org's 5 fixed subdomains. See scripts/llms_common.py for the shared
frontmatter/structural-analysis helpers used by this and its siblings
(llms_coverage.py, llms_fidelity.py).

SCOPE CUT (stated honestly, not silently): this generates flat per-page
.txt files with a header block plus a root llms.txt index per site type.
It does NOT implement source's nested per-product llms.txt hierarchy,
provenance-hash manifest, or live-HTTP deploy verification -- those are
deferred (see docs/parity/source-anchors.yaml, TASK_BACKLOG.md).

Usage:
    .venv/bin/python scripts/llms_generate.py --output llms-output
    .venv/bin/python scripts/llms_generate.py --output llms-output --sites docs,kb
    .venv/bin/python scripts/llms_generate.py --output llms-output --clean-output

Idempotent: running twice with unchanged source content produces byte-identical
output (deterministic sorted file order, no timestamps in generated bodies).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config, resolve_content_repo, ConfigError
from llms_common import (
    extract_title,
    is_eligible_page,
    iter_site_pages,
    parse_frontmatter,
)


def render_page(source_path: Path, content_root: Path, site_type: str) -> "tuple[str, str] | None":
    """Return (relative_output_path, rendered_text), or None if ineligible."""
    text = source_path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = parse_frontmatter(text)
    if not is_eligible_page(frontmatter):
        return None

    title = extract_title(frontmatter, body)
    rel_source = source_path.relative_to(content_root)
    header_lines = [
        f"Site: {site_type}",
        f"Title: {title}",
        f"Source: {rel_source.as_posix()}",
        "",
    ]
    rendered = "\n".join(header_lines) + body.strip() + "\n"
    rel_output = rel_source.with_suffix(".txt")
    return rel_output.as_posix(), rendered


def generate_site(content_root: Path, output_root: Path, site_type: str, content_path_template: str) -> list:
    """Generate all eligible pages for one site type. Returns the sorted list
    of (relative_output_path, title) tuples written, for the index."""
    written = []
    site_output_dir = output_root / site_type
    for source_path in iter_site_pages(content_root, content_path_template):
        result = render_page(source_path, content_root, site_type)
        if result is None:
            continue
        rel_output, rendered = result
        out_path = site_output_dir / rel_output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        frontmatter, body = parse_frontmatter(source_path.read_text(encoding="utf-8", errors="replace"))
        written.append((rel_output, extract_title(frontmatter, body)))

    index_lines = [f"# {site_type} -- {len(written)} page(s)", ""]
    for rel_output, title in sorted(written):
        index_lines.append(f"- {rel_output}: {title}")
    (site_output_dir).mkdir(parents=True, exist_ok=True)
    (site_output_dir / "llms.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    return written


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="llms-output", help="Output directory")
    parser.add_argument("--sites", default=None,
                         help="Comma-separated site types to generate (default: all configured sites)")
    parser.add_argument("--clean-output", action="store_true", help="Remove the output directory first")
    parser.add_argument("--content-root", default=None,
                         help="Override content root (default: resolved via config.yaml/CONTENT_REPO_PATH)")
    args = parser.parse_args(argv)

    try:
        config = load_config()
        content_root = Path(args.content_root) if args.content_root else resolve_content_repo()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sites = config.get("sites", {})
    if not sites:
        print("ERROR: config.yaml has no sites: block configured.", file=sys.stderr)
        return 2

    site_types = args.sites.split(",") if args.sites else sorted(sites.keys())
    output_root = Path(args.output)

    if args.clean_output and output_root.exists():
        shutil.rmtree(output_root)

    total = 0
    for site_type in site_types:
        site_cfg = sites.get(site_type)
        if not site_cfg or "content_path" not in site_cfg:
            print(f"WARNING: unknown or misconfigured site type {site_type!r} -- skipping", file=sys.stderr)
            continue
        written = generate_site(content_root, output_root, site_type, site_cfg["content_path"])
        print(f"[{site_type}] {len(written)} page(s) written")
        total += len(written)

    print(f"\nTotal: {total} page(s) across {len(site_types)} site(s) -> {output_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
