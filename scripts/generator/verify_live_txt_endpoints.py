#!/usr/bin/env python3
"""TC-11: Verify live .txt endpoints after production deploy.

Reads generated-txt-inventory.json, samples ~50% of URLs per domain,
checks HTTP status and content quality. Retries with backoff.

Output: reports/llms-txt-verification/live-verification-results.json
        reports/llms-txt-verification/failures.md (if any)
"""
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error

PILOT_PAGES = {
    'products.aspose.org': ['cells.txt', 'cells/python.txt'],
    'docs.aspose.org': ['cells/java.txt', 'cells/java/getting-started/quickstart.txt'],
    'kb.aspose.org': ['3d/java/how-to-load-3d-models-java.txt'],
    'reference.aspose.org': ['cells/java/AlignmentValue.txt'],
    'blog.aspose.org': [],
}

CONTENT_CHECKS = [
    ('no_angle_shortcodes', lambda body: '{{' not in body),
    ('no_percent_shortcodes', lambda body: '{%' not in body),
    ('has_title', lambda body: body.startswith('# ')),
    ('has_url', lambda body: 'https://' in body),
    ('no_evidence', lambda body: 'claim_id' not in body and 'model_sha' not in body),
    ('no_grading', lambda body: 'graded_content_hash' not in body),
]


def check_url(url, retries=3, backoff=2.0):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=15) as r:
                return {
                    'url': url, 'status': r.status,
                    'content_type': r.headers.get('Content-Type', ''),
                    'cache_control': r.headers.get('Cache-Control', ''),
                    'pass': r.status == 200, 'attempts': attempt + 1
                }
        except urllib.error.HTTPError as e:
            if e.code in (404, 403, 410):
                return {'url': url, 'status': e.code, 'pass': False, 'attempts': attempt + 1}
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    return {'url': url, 'status': 0, 'pass': False, 'error': 'timeout after retries', 'attempts': retries}


def check_content(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            body = r.read(4096).decode('utf-8', errors='replace')
        results = {}
        for name, fn in CONTENT_CHECKS:
            results[name] = fn(body)
        results['first_line'] = body.split('\n')[0][:100]
        results['pass'] = all(results[name] for name, _ in CONTENT_CHECKS)
        return results
    except Exception as e:
        return {'pass': False, 'error': str(e)}


def select_sample(domain, urls):
    pilot_urls = {f'https://{domain}/{p}' for p in PILOT_PAGES.get(domain, [])}
    if domain == 'blog.aspose.org' and urls:
        pilot_urls.add(urls[0])
    n = len(urls)
    target = max(1, math.ceil(n * 0.50))
    step = max(1, n // target)
    sampled = set(urls[i] for i in range(0, n, step))
    sampled.update(pilot_urls & set(urls))
    return sorted(sampled)[:target + len(pilot_urls)]


def main():
    inv_path = 'reports/llms-txt-verification/generated-txt-inventory.json'
    if not os.path.exists(inv_path):
        print(f"ERROR: {inv_path} not found — run build_txt_inventory.py first", file=sys.stderr)
        sys.exit(1)

    with open(inv_path) as f:
        inventory = json.load(f)

    out_dir = 'reports/llms-txt-verification'
    os.makedirs(out_dir, exist_ok=True)

    all_results = {}
    domain_summaries = []
    any_failure = False

    for domain, urls in inventory.items():
        print(f"\n=== {domain}: {len(urls)} total, sampling ~50% ===")
        sample = select_sample(domain, urls)
        domain_pass = 0
        domain_fail = 0
        domain_results = []

        for url in sample:
            result = check_url(url)
            domain_results.append(result)
            if result['pass']:
                ct = result.get('content_type', '')
                if 'octet-stream' in ct:
                    result['pass'] = False
                    result['mime_fail'] = True
            if result['pass']:
                domain_pass += 1
            else:
                domain_fail += 1
                any_failure = True
                print(f"  FAIL {url} status={result.get('status')} ct={result.get('content_type', '?')}")

        spot_url = next((r['url'] for r in domain_results if r['pass']), None)
        spot_result = check_content(spot_url) if spot_url else {'pass': False, 'error': 'no passing URL'}
        if not spot_result.get('pass'):
            print(f"  CONTENT FAIL {spot_url}: {spot_result}")
            any_failure = True

        all_results[domain] = {'urls': domain_results, 'spot_check': spot_result}
        domain_summaries.append({
            'domain': domain, 'total': len(urls), 'sampled': len(sample),
            'passed': domain_pass, 'failed': domain_fail,
            'content_pass': spot_result.get('pass', False),
            'first_line': spot_result.get('first_line', ''),
            'content_type': domain_results[0].get('content_type', '') if domain_results else ''
        })
        print(f"  {domain}: {domain_pass}/{len(sample)} HTTP OK, content={'PASS' if spot_result.get('pass') else 'FAIL'}")

    with open(f'{out_dir}/live-verification-results.json', 'w') as f:
        json.dump(all_results, f, indent=2)

    failures = [r for d in all_results.values() for r in d.get('urls', []) if not r['pass']]
    if failures:
        with open(f'{out_dir}/failures.md', 'w') as f:
            f.write('# TC-11 Failures\n\n')
            for r in failures:
                f.write(f"- `{r['url']}` status={r.get('status')} ct={r.get('content_type', '')} error={r.get('error', '')}\n")

    print("\n=== TC-11 Summary ===")
    for s in domain_summaries:
        status = 'PASS' if s['failed'] == 0 and s['content_pass'] else 'FAIL'
        print(f"  {s['domain']}: {s['passed']}/{s['sampled']} HTTP | content={status} | ct={s['content_type'][:30]}")

    # TC-07 decision
    all_ct = [u.get('content_type', '') for d in all_results.values() for u in d.get('urls', []) if u.get('pass')]
    bad = [ct for ct in all_ct if 'octet-stream' in ct]
    print(f"\nTC-07 decision: {'MANDATORY' if bad else 'DEFERRED (all text/plain)'}")

    sys.exit(1 if any_failure else 0)


if __name__ == '__main__':
    main()
