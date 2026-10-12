#!/usr/bin/env python3
"""
detect_stale_llms.py — Stale LLMs Output Detector

Maintains a provenance manifest mapping each .txt output to its source .md,
source hash (sha256), and generation timestamp.

Usage:
    # Update manifest (record current hashes):
    .venv/Scripts/python scripts/generator/detect_stale_llms.py \\
        --llms-output llms-output --content content --update-manifest

    # Check for stale/missing outputs (exit 1 if any found):
    .venv/Scripts/python scripts/generator/detect_stale_llms.py --check-only

Outputs (LOCAL ONLY — reports/ is gitignored):
    reports/agent-consumption/provenance-manifest.json
    reports/agent-consumption/stale-report.json
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

MANIFEST_PATH = 'reports/agent-consumption/provenance-manifest.json'
STALE_REPORT_PATH = 'reports/agent-consumption/stale-report.json'

DOMAINS = [
    'blog.aspose.org',
    'docs.aspose.org',
    'kb.aspose.org',
    'products.aspose.org',
    'reference.aspose.org',
]

# Files excluded from stale tracking (discovery indexes, not per-page outputs)
EXCLUDED_NAMES = {'llms.txt', 'llms-full.txt'}


def _sha256_file(path: str) -> Optional[str]:
    """Return sha256 hex digest of file contents, or None if unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _is_nested_llms(rel_path: str) -> bool:
    """Return True if this is a nested llms.txt (e.g. pdf/net/llms.txt)."""
    parts = rel_path.replace('\\', '/').split('/')
    return parts[-1] == 'llms.txt' and len(parts) > 1


def _derive_source_path(txt_path: str, llms_output_base: str, content_base: str) -> Optional[str]:
    """
    Reverse-map a .txt output path to its likely source .md path.

    The generator path derivation is:
      content/{domain}/en/{family}/{platform}/{slug}.md
        -> llms-output/{domain}/{family}/{platform}/{slug}.txt

    For index files:
      content/{domain}/en/{family}/{platform}/_index.md
        -> llms-output/{domain}/{family}/{platform}.txt

    Returns the source .md path (first match found), or None.
    """
    txt_abs = os.path.abspath(txt_path)
    output_abs = os.path.abspath(llms_output_base)
    content_abs = os.path.abspath(content_base)

    rel = os.path.relpath(txt_abs, output_abs).replace('\\', '/')
    # rel example: 'reference.aspose.org/pdf/net/Document.txt'
    # Remove .txt extension
    if not rel.endswith('.txt'):
        return None
    rel_md = rel[:-4] + '.md'

    # Candidate 1: direct mapping (leaf page)
    # rel_md: 'reference.aspose.org/pdf/net/Document.md'
    # -> content/reference.aspose.org/en/pdf/net/Document.md
    parts = rel_md.split('/')
    domain_part = parts[0]
    rest_parts = parts[1:]  # e.g. ['pdf', 'net', 'Document.md'] or ['index.md']
    rest = '/'.join(rest_parts)  # 'pdf/net/Document.md'

    # Special case: root index.md (generated from domain root _index.md)
    # rel_md = 'docs.aspose.org/index.md'  -> content/docs.aspose.org/en/_index.md
    if rest == 'index.md':
        for idx_name in ('_index.md', 'index.md'):
            for candidate in [
                os.path.normpath(os.path.join(content_abs, domain_part, 'en', idx_name)),
                os.path.normpath(os.path.join(content_abs, domain_part, idx_name)),
            ]:
                if os.path.exists(candidate):
                    return candidate
        return None

    # Try with /en/ injection (direct leaf page)
    candidate1 = os.path.normpath(os.path.join(content_abs, domain_part, 'en', rest))
    if os.path.exists(candidate1):
        return candidate1

    # Try without /en/ (blog uses flat structure)
    candidate2 = os.path.normpath(os.path.join(content_abs, domain_part, rest))
    if os.path.exists(candidate2):
        return candidate2

    # Candidate 2: index file mapping
    # rel_md: 'reference.aspose.org/pdf/net.md'  -> _index.md under pdf/net/
    base = os.path.basename(rel_md)     # 'net.md'
    stem = base[:-3]                    # 'net'
    parent_rel = '/'.join(rel_md.split('/')[1:-1])  # 'pdf'
    dir_path_en = os.path.join(content_abs, domain_part, 'en', parent_rel, stem)
    dir_path_flat = os.path.join(content_abs, domain_part, parent_rel, stem)

    for dir_candidate in [dir_path_en, dir_path_flat]:
        for idx_name in ('_index.md', 'index.md'):
            idx_path = os.path.normpath(os.path.join(dir_candidate, idx_name))
            if os.path.exists(idx_path):
                return idx_path

    return None


def walk_txt_outputs(llms_output_base: str):
    """
    Yield (domain, rel_path, abs_txt_path) for all trackable .txt page files.
    Excludes root llms.txt, llms-full.txt, and nested llms.txt indexes.
    """
    base = os.path.abspath(llms_output_base)
    for domain in DOMAINS:
        domain_dir = os.path.join(base, domain)
        if not os.path.isdir(domain_dir):
            continue
        for root, _, files in os.walk(domain_dir):
            for fname in sorted(files):
                if not fname.endswith('.txt'):
                    continue
                abs_path = os.path.join(root, fname)
                rel = os.path.relpath(abs_path, domain_dir).replace('\\', '/')
                # Exclude root-level discovery files
                if rel in EXCLUDED_NAMES:
                    continue
                # Exclude nested llms.txt indexes
                if _is_nested_llms(rel):
                    continue
                full_rel = domain + '/' + rel
                yield domain, rel, abs_path, full_rel


def build_manifest(llms_output_base: str, content_base: str) -> dict:
    """Build a fresh provenance manifest by hashing all source .md files."""
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    pages = {}

    for domain, rel, abs_txt, full_rel in walk_txt_outputs(llms_output_base):
        source_path = _derive_source_path(abs_txt, llms_output_base, content_base)
        source_hash = _sha256_file(source_path) if source_path else None

        pages[full_rel] = {
            'source_path': source_path,
            'source_hash': source_hash,
            'generated_at': now,
            'status': 'CURRENT' if source_path and source_hash else 'NO_SOURCE',
        }

    return {
        'manifest_version': '1.0',
        'generated_at': now,
        'page_count': len(pages),
        'pages': pages,
    }


def detect_issues(manifest: dict, llms_output_base: str, content_base: str) -> dict:
    """
    Compare manifest against current file state.

    Returns:
        {
            'stale':   [(full_rel, old_hash, new_hash), ...],
            'missing': [(full_rel, source_path), ...],
            'orphan':  [(full_rel, abs_txt), ...],
        }
    """
    recorded = set(manifest.get('pages', {}).keys())
    stale = []
    missing = []

    for full_rel, entry in manifest.get('pages', {}).items():
        source_path = entry.get('source_path')
        old_hash = entry.get('source_hash')

        if not source_path or not os.path.exists(source_path):
            # source deleted — treated as missing (regeneration will fix)
            missing.append((full_rel, source_path or '(unknown)'))
            continue

        new_hash = _sha256_file(source_path)
        if new_hash != old_hash:
            stale.append((full_rel, old_hash, new_hash))

    # Orphan: .txt files present that are NOT in manifest
    # (new files would be MISSING from manifest until update-manifest is run)
    live_set = set()
    for domain, rel, abs_txt, full_rel in walk_txt_outputs(llms_output_base):
        live_set.add(full_rel)

    # MISSING: recorded in manifest but .txt no longer exists
    for full_rel in recorded:
        # Derive abs_txt path
        abs_txt = os.path.join(
            os.path.abspath(llms_output_base),
            full_rel.replace('/', os.sep)
        )
        if not os.path.exists(abs_txt):
            # source entry recorded but output file deleted
            source_path = manifest['pages'][full_rel].get('source_path', '(unknown)')
            if not any(fr == full_rel for fr, _ in missing):
                missing.append((full_rel, source_path))

    return {'stale': stale, 'missing': missing, 'orphan': []}


def load_manifest(manifest_path: str = MANIFEST_PATH) -> Optional[dict]:
    """Load manifest from disk, or return None if not found."""
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_manifest(manifest: dict, manifest_path: str = MANIFEST_PATH) -> None:
    os.makedirs(os.path.dirname(manifest_path) or '.', exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest written: {manifest_path} ({manifest['page_count']} pages)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Detect stale llms-output files')
    parser.add_argument('--llms-output', default='llms-output',
                        help='llms-output root directory')
    parser.add_argument('--content', default='content',
                        help='Hugo content root directory')
    parser.add_argument('--update-manifest', action='store_true',
                        help='Build and save fresh provenance manifest')
    parser.add_argument('--check-only', action='store_true',
                        help='Read existing manifest and report issues (exit 1 if any)')
    parser.add_argument('--manifest-path', default=MANIFEST_PATH,
                        help='Path to read/write the provenance manifest (MT069 HC-12: point this at a '
                             'manifest PERSISTED FROM A PRIOR RUN to make --check-only a genuine cross-run '
                             'drift check. Passing the SAME run\'s own --update-manifest output right back '
                             'into --check-only is vacuous by construction -- it re-hashes the same, '
                             'unchanged source files the manifest was just built from and can never find '
                             'drift. See scripts/ci/deployed-workflows/llms-generation.yml for the pattern.')
    parser.add_argument('--stale-report-path', default=STALE_REPORT_PATH,
                        help='Path to write the stale report')
    args = parser.parse_args(argv)

    if not args.update_manifest and not args.check_only:
        parser.error('Specify --update-manifest or --check-only')

    if args.update_manifest:
        print('Building provenance manifest...')
        manifest = build_manifest(args.llms_output, args.content)
        save_manifest(manifest, args.manifest_path)
        if not args.check_only:
            return 0

    # --check-only (or update-manifest + check)
    manifest = load_manifest(args.manifest_path)
    if manifest is None:
        print(f'ERROR: No manifest found at {args.manifest_path}. Run --update-manifest first.', file=sys.stderr)
        return 1

    print(f'Checking manifest ({manifest["page_count"]} pages)...')
    issues = detect_issues(manifest, args.llms_output, args.content)

    stale = issues['stale']
    missing = issues['missing']

    # Write stale report
    os.makedirs(os.path.dirname(args.stale_report_path) or '.', exist_ok=True)
    report = {
        'checked_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'manifest_path': args.manifest_path,
        'stale_count': len(stale),
        'missing_count': len(missing),
        'stale': [{'path': fr, 'old_hash': oh, 'new_hash': nh}
                  for fr, oh, nh in stale],
        'missing': [{'path': fr, 'source_path': sp} for fr, sp in missing],
    }
    with open(args.stale_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    if stale:
        print(f'STALE ({len(stale)}):')
        for fr, oh, nh in stale[:10]:
            print(f'  {fr}')
        if len(stale) > 10:
            print(f'  ... and {len(stale) - 10} more')

    if missing:
        print(f'MISSING ({len(missing)}):')
        for fr, sp in missing[:10]:
            print(f'  {fr}  (source: {sp})')
        if len(missing) > 10:
            print(f'  ... and {len(missing) - 10} more')

    if not stale and not missing:
        print(f'OK: 0 STALE, 0 MISSING')
        print(f'Report: {args.stale_report_path}')
        return 0
    else:
        print(f'\nFAIL: {len(stale)} STALE, {len(missing)} MISSING')
        print(f'Report: {args.stale_report_path}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
