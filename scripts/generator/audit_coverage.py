#!/usr/bin/env python3
"""
audit_coverage.py — Agent-Consumption Coverage Auditor

Walks the Hugo content directories, applies the same eligibility rules as
llms-generator.py, and compares against actual .txt output files in llms-output/.

Output: reports/agent-consumption/coverage-report.json (LOCAL ONLY — gitignored)

Usage:
    python scripts/generator/audit_coverage.py \
        --content content \
        --llms-output llms-output \
        --output reports/agent-consumption/coverage-report.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

DOMAINS = [
    'blog.aspose.org',
    'docs.aspose.org',
    'kb.aspose.org',
    'products.aspose.org',
    'reference.aspose.org',
]

INDEX_FILES = {'_index.md', 'index.md'}


def is_index_file(filename: str) -> bool:
    return filename.lower() in INDEX_FILES


def is_draft(filepath: str) -> bool:
    """Return True if the file has draft: true in frontmatter."""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            content = f.read(2000)
        if not content.startswith('---'):
            return False
        end = content.find('---', 3)
        if end == -1:
            return False
        fm = content[3:end]
        return bool(re.search(r'^\s*draft\s*:\s*true\s*$', fm, re.MULTILINE | re.IGNORECASE))
    except OSError:
        return False


def derive_output_txt_path(input_path: str, content_base: str, llms_output_base: str) -> str:
    """
    Replicate llms-generator.py's output path derivation.
    Returns the expected .txt path for the given .md input.
    """
    out_path = input_path.replace(content_base, llms_output_base)

    # Strip /en/ directory segment
    out_path = out_path.replace(os.sep + 'en' + os.sep, os.sep)

    filename = os.path.basename(input_path)
    if is_index_file(filename):
        # index.md / _index.md → {parent}.md (then .txt)
        parent_dir = os.path.dirname(out_path)
        base = os.path.basename(parent_dir)
        grandparent = os.path.dirname(parent_dir)
        out_path = os.path.join(grandparent, f'{base}.md')

    # Change .md to .txt
    assert out_path.endswith('.md'), f"Expected .md path: {out_path}"
    return out_path[:-3] + '.txt'


def audit_domain(domain: str, content_base: str, llms_output_base: str) -> dict:
    """
    Walk content/{domain}/, apply eligibility rules, check for .txt output.
    Returns coverage stats dict.
    """
    domain_content_dir = os.path.join(content_base, domain)
    if not os.path.isdir(domain_content_dir):
        return {
            'total_eligible': 0,
            'has_output': 0,
            'missing_count': 0,
            'coverage_pct': 0.0,
            'missing_pages': [],
            'error': f'content dir not found: {domain_content_dir}',
        }

    eligible = []
    missing = []
    covered = []

    for root, dirs, files in os.walk(domain_content_dir):
        # Sort for determinism; skip non-EN locale folders
        dirs[:] = sorted(
            d for d in dirs
            if not (re.fullmatch(r'[a-z]{2}', d) and d != 'en')
        )

        for filename in sorted(files):
            if not filename.lower().endswith('.md'):
                continue

            # Skip locale-suffixed filenames (e.g., index.es.md)
            if re.search(r'\.[a-z]{2}\.md$', filename.lower()):
                continue

            input_path = os.path.join(root, filename)

            # Skip draft pages
            if is_draft(input_path):
                continue

            eligible.append(input_path)

            # Derive expected .txt output path
            expected_txt = derive_output_txt_path(input_path, content_base, llms_output_base)

            if os.path.exists(expected_txt):
                covered.append(input_path)
            else:
                # Build a human-readable relative path for reporting
                rel = os.path.relpath(input_path, content_base).replace(os.sep, '/')
                missing.append(rel)

    total = len(eligible)
    has_output = len(covered)
    pct = (has_output / total * 100) if total > 0 else 0.0

    return {
        'total_eligible': total,
        'has_output': has_output,
        'missing_count': len(missing),
        'coverage_pct': round(pct, 2),
        'missing_pages': missing,
    }


def print_table(results: dict) -> None:
    """Print ASCII summary table to stdout."""
    header = f"{'Domain':<35} {'Eligible':>9} {'Has output':>10} {'Missing':>8} {'Coverage':>9}"
    print(header)
    print('-' * len(header))
    for domain, stats in results.items():
        if 'error' in stats:
            print(f"{domain:<35}  ERROR: {stats['error']}")
            continue
        print(
            f"{domain:<35} {stats['total_eligible']:>9} {stats['has_output']:>10} "
            f"{stats['missing_count']:>8} {stats['coverage_pct']:>8.1f}%"
        )
    all_eligible = sum(s.get('total_eligible', 0) for s in results.values())
    all_has = sum(s.get('has_output', 0) for s in results.values())
    all_missing = sum(s.get('missing_count', 0) for s in results.values())
    overall = (all_has / all_eligible * 100) if all_eligible > 0 else 0.0
    print('-' * len(header))
    print(f"{'TOTAL':<35} {all_eligible:>9} {all_has:>10} {all_missing:>8} {overall:>8.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description='Agent-consumption coverage auditor')
    parser.add_argument('--content', default='content', help='Hugo content root')
    parser.add_argument('--llms-output', default='llms-output', help='llms-output root')
    parser.add_argument('--output', default='reports/agent-consumption/coverage-report.json',
                        help='Output report path')
    parser.add_argument('--domains', nargs='+', default=DOMAINS,
                        help='Domains to audit (default: all 5)')
    args = parser.parse_args()

    content_base = os.path.abspath(args.content)
    llms_output_base = os.path.abspath(args.llms_output)

    results = {}
    for domain in args.domains:
        print(f"Auditing {domain}...")
        results[domain] = audit_domain(domain, content_base, llms_output_base)

    print()
    print_table(results)

    # Check gate
    failed = [k for k, v in results.items() if v.get('coverage_pct', 0) < 95]
    if failed:
        print(f"\nWARNING: Coverage <95% for: {', '.join(failed)}")
    else:
        print("\nPASS: All domains >=95% coverage")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"Report written: {args.output}")

    if any('error' in v for v in results.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
