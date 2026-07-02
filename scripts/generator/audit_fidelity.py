#!/usr/bin/env python3
"""
audit_fidelity.py — Agent-Consumption Fidelity Auditor

Samples pages from content/ and their corresponding .txt outputs in llms-output/,
scoring fidelity across key structural dimensions:
  - title_preserved: H1 in output matches source title
  - h2_count_ok: output H2 count >= source H2 count
  - code_fence_count_ok: output code fences >= source code fences
  - table_row_count_ok: output table rows >= source table rows
  - no_shortcode: no '{{' or '{%' in output
  - no_evidence_field: no 'claim_id:' / 'model_sha:' leakage in output

Score: (pass_count / applicable_checks) * 100 per page.
Overall score: mean of page scores.

Gate: overall_score >= 90

Usage:
    python scripts/generator/audit_fidelity.py \
        --content content \
        --output-dir llms-output \
        --report reports/agent-consumption/fidelity-report.json

    # Full corpus (no sampling):
    python scripts/generator/audit_fidelity.py ... --full-corpus
"""

import argparse
import json
import os
import random
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
SAMPLE_PER_DOMAIN = 10
RANDOM_SEED = 42

# Threshold for an individual page to be considered passing
PAGE_PASS_THRESHOLD = 80.0
# Threshold for overall fidelity gate
OVERALL_PASS_THRESHOLD = 90.0


def is_index_file(filename: str) -> bool:
    return filename.lower() in INDEX_FILES


def extract_frontmatter_title(text: str) -> str:
    """Extract `title:` value from YAML frontmatter."""
    if not text.startswith('---'):
        return ''
    end = text.find('---', 3)
    if end == -1:
        return ''
    fm = text[3:end]
    m = re.search(r'^title\s*:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ''


def count_h1(text: str) -> int:
    return len(re.findall(r'^# .+', text, re.MULTILINE))


def count_h2(text: str) -> int:
    return len(re.findall(r'^## .+', text, re.MULTILINE))


def count_code_fences(text: str) -> int:
    return text.count('```')


def count_table_rows(text: str) -> int:
    return len([l for l in text.splitlines() if l.strip().startswith('|')])


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter, returning just the body."""
    if text.startswith('---'):
        end = text.find('---', 3)
        if end != -1:
            return text[end + 3:].lstrip()
    return text


def has_shortcode(text: str) -> bool:
    return '{{' in text or '{%' in text


def has_evidence_leakage(text: str) -> bool:
    patterns = ['claim_id:', 'model_sha:', 'model_version:', 'content_hash:',
                'content_origin:', 'auto_updatable:']
    for p in patterns:
        if p in text:
            return True
    return False


def score_page(source_path: str, output_txt_path: str) -> dict:
    """
    Compare source .md and output .txt; return per-page fidelity scores.
    """
    result = {
        'source': source_path,
        'output': output_txt_path,
        'checks': {},
        'score': 0.0,
        'status': 'ok',
    }

    try:
        with open(source_path, encoding='utf-8', errors='replace') as f:
            src_text = f.read()
    except OSError as e:
        result['status'] = f'source_read_error: {e}'
        return result

    if not os.path.exists(output_txt_path):
        result['status'] = 'output_missing'
        return result

    try:
        with open(output_txt_path, encoding='utf-8', errors='replace') as f:
            out_text = f.read()
    except OSError as e:
        result['status'] = f'output_read_error: {e}'
        return result

    src_body = strip_frontmatter(src_text)

    # --- Check dimensions ---
    checks = {}

    # Title preserved: frontmatter title should appear in first 10 lines of output.
    # (10 lines to accommodate the 6-line page header block prepended by TC-W4-003)
    fm_title = extract_frontmatter_title(src_text)
    if fm_title:
        out_first = '\n'.join(out_text.splitlines()[:10]).lower()
        checks['title_preserved'] = fm_title.lower() in out_first
    # (skip check if no frontmatter title — not applicable)

    # H2 count: output >= source (headings not dropped)
    src_h2 = count_h2(src_body)
    out_h2 = count_h2(out_text)
    if src_h2 > 0:
        checks['h2_count_ok'] = out_h2 >= src_h2

    # Code fences: output >= source
    src_fences = count_code_fences(src_body)
    out_fences = count_code_fences(out_text)
    if src_fences > 0:
        checks['code_fence_count_ok'] = out_fences >= src_fences

    # Table rows: output >= source
    src_tables = count_table_rows(src_body)
    out_tables = count_table_rows(out_text)
    if src_tables > 0:
        checks['table_row_count_ok'] = out_tables >= src_tables

    # No shortcodes leaked into output
    checks['no_shortcode'] = not has_shortcode(out_text)

    # No evidence fields leaked into output
    checks['no_evidence_field'] = not has_evidence_leakage(out_text)

    result['checks'] = checks
    result['src_h2'] = src_h2
    result['out_h2'] = out_h2
    result['src_fences'] = src_fences
    result['out_fences'] = out_fences
    result['src_tables'] = src_tables
    result['out_tables'] = out_tables

    # Score = fraction of applicable checks that pass
    if checks:
        passed = sum(1 for v in checks.values() if v)
        result['score'] = round(passed / len(checks) * 100, 1)
    else:
        result['score'] = 100.0  # No applicable checks — trivially passing

    return result


def derive_output_txt(input_path: str, content_base: str, llms_output_base: str) -> str:
    """Replicate generator path derivation (same as audit_coverage.py)."""
    out = input_path.replace(content_base, llms_output_base)
    out = out.replace(os.sep + 'en' + os.sep, os.sep)
    filename = os.path.basename(input_path)
    if filename.lower() in INDEX_FILES:
        parent_dir = os.path.dirname(out)
        base = os.path.basename(parent_dir)
        grandparent = os.path.dirname(parent_dir)
        out = os.path.join(grandparent, f'{base}.md')
    assert out.endswith('.md'), f"Expected .md: {out}"
    return out[:-3] + '.txt'


def collect_eligible_pages(domain: str, content_base: str, llms_output_base: str) -> list:
    """Walk content/{domain}/ and collect (source_path, output_txt_path) pairs that both exist."""
    domain_dir = os.path.join(content_base, domain)
    if not os.path.isdir(domain_dir):
        return []

    pairs = []
    for root, dirs, files in os.walk(domain_dir):
        dirs[:] = sorted(
            d for d in dirs
            if not (re.fullmatch(r'[a-z]{2}', d) and d != 'en')
        )
        for filename in sorted(files):
            if not filename.lower().endswith('.md'):
                continue
            if re.search(r'\.[a-z]{2}\.md$', filename.lower()):
                continue
            input_path = os.path.join(root, filename)
            try:
                output_txt = derive_output_txt(input_path, content_base, llms_output_base)
            except AssertionError:
                continue
            if os.path.exists(output_txt):
                pairs.append((input_path, output_txt))

    return pairs


def audit_domain(domain: str, content_base: str, llms_output_base: str,
                 full_corpus: bool = False, n_sample: int = SAMPLE_PER_DOMAIN) -> dict:
    """Run fidelity audit for one domain."""
    pairs = collect_eligible_pages(domain, content_base, llms_output_base)

    if not pairs:
        return {'status': 'no_pages', 'page_count': 0, 'domain_score': 0.0, 'pages': []}

    if full_corpus:
        sample = pairs
    else:
        rng = random.Random(RANDOM_SEED)
        sample = rng.sample(pairs, min(n_sample, len(pairs)))

    page_results = []
    for src, out in sample:
        page_results.append(score_page(src, out))

    valid_scores = [p['score'] for p in page_results if p['status'] == 'ok']
    domain_score = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 0.0

    failing = [p for p in page_results if p.get('score', 0) < PAGE_PASS_THRESHOLD]

    return {
        'status': 'ok',
        'total_pairs': len(pairs),
        'sampled': len(sample),
        'domain_score': domain_score,
        'failing_pages': len(failing),
        'pages': page_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Agent-consumption fidelity auditor')
    parser.add_argument('--content', default='content')
    parser.add_argument('--output-dir', default='llms-output')
    parser.add_argument('--report', default='reports/agent-consumption/fidelity-report.json')
    parser.add_argument('--domains', nargs='+', default=DOMAINS)
    parser.add_argument('--full-corpus', action='store_true',
                        help='Audit all pages, not just a sample')
    parser.add_argument('--sample-size', type=int, default=SAMPLE_PER_DOMAIN,
                        help='Pages per domain when sampling (default 10)')
    args = parser.parse_args()

    content_base = os.path.abspath(args.content)
    llms_output_base = os.path.abspath(args.output_dir)

    domain_results = {}
    all_scores = []

    for domain in args.domains:
        mode = 'full corpus' if args.full_corpus else f'sample n={args.sample_size}'
        print(f"Auditing {domain} ({mode})...")
        result = audit_domain(domain, content_base, llms_output_base,
                              full_corpus=args.full_corpus, n_sample=args.sample_size)
        domain_results[domain] = result
        if result['domain_score'] > 0:
            all_scores.append(result['domain_score'])

    overall = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0

    print()
    print(f"{'Domain':<35} {'Pages':>6} {'Sampled':>8} {'Score':>8} {'Failing':>8}")
    print('-' * 70)
    for domain, r in domain_results.items():
        if r['status'] == 'no_pages':
            print(f"{domain:<35}  (no eligible pages)")
            continue
        print(
            f"{domain:<35} {r['total_pairs']:>6} {r['sampled']:>8} "
            f"{r['domain_score']:>7.1f}% {r['failing_pages']:>8}"
        )
    print('-' * 70)
    print(f"{'OVERALL':<35} {'':>6} {'':>8} {overall:>7.1f}%")

    gate = 'PASS' if overall >= OVERALL_PASS_THRESHOLD else 'FAIL'
    print(f"\nFidelity gate ({OVERALL_PASS_THRESHOLD}%): {gate}")

    report = {
        'overall_score': overall,
        'gate_threshold': OVERALL_PASS_THRESHOLD,
        'gate': gate,
        'full_corpus': args.full_corpus,
        'domains': domain_results,
    }

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"Report written: {args.report}")

    if gate == 'FAIL':
        sys.exit(1)


if __name__ == '__main__':
    main()
