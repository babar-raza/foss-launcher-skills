"""llms_verify.py -- verify live HTTP endpoints for deployed llms-output pages.

Generalized from aspose.org's S-LG-02 llms-verify skill (deferred at first,
now ported as TASK_BACKLOG.md SYNC-6). Source hardcodes 5 aspose.org
subdomains and a deploy-specific URL-mapping file; this port instead reads
an OPTIONAL `base_url` field per site in config.yaml's sites: block (absent
by default -- sites with no public deploy are simply skipped, not an error).

URL construction is intentionally simple and stated as such: `base_url +
"/" + relative .txt path` (mirroring llms_generate.py's own flat output
layout 1:1). Source's more elaborate URL-mapping file is not ported --
sites whose deployed URL structure differs from their llms-output/ layout
need a mapping this script does not yet provide; that gap is real, not
hidden (see the module docstring's SCOPE CUT note below is intentionally
brief -- this is a v1, not a claim of universal URL-mapping support).

Usage:
    .venv/bin/python scripts/llms_generate.py --output llms-output   # first
    .venv/bin/python scripts/llms_verify.py --output llms-output --report reports/llms-verify.json
    .venv/bin/python scripts/llms_verify.py --output llms-output --gate 95

Exit codes (only meaningful with --gate):
  0 -- pass rate at or above the gate threshold (or nothing to verify)
  1 -- pass rate below threshold
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config, ConfigError
from llms_common import structural_counts

_DEFAULT_TIMEOUT = 10


def default_fetch(url: str, timeout: int = _DEFAULT_TIMEOUT) -> "tuple[int, str, str]":
    """Real HTTP GET. Returns (status_code, content_type, body). Injected as
    a parameter everywhere else in this module so tests never need a real
    network call -- see tests/test_llms_verify.py's in-process local HTTP
    server fixture for the non-mocked, real-socket proof."""
    req = urllib.request.Request(url, headers={"User-Agent": "llms-verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            content_type = resp.headers.get("Content-Type", "")
            return resp.status, content_type, body
    except urllib.error.HTTPError as exc:
        return exc.code, "", ""
    except urllib.error.URLError:
        return 0, "", ""


def check_page(url: str, body: str, status: int, content_type: str) -> dict:
    checks = {
        "http_200": status == 200,
        "content_type_text": content_type.startswith("text/") or content_type == "",
    }
    if checks["http_200"]:
        counts = structural_counts(body)
        checks["no_shortcode"] = not counts["has_shortcode"]
        checks["no_evidence_leak"] = not counts["has_evidence_field"]
        checks["has_content"] = len(body.strip()) > 0
    ok = all(checks.values())
    return {"url": url, "status": status, "ok": ok, "checks": checks}


def verify_site(output_root: Path, site_type: str, base_url: str, fetch=default_fetch) -> list:
    site_dir = output_root / site_type
    results = []
    if not site_dir.is_dir():
        return results
    for txt_path in sorted(site_dir.rglob("*.txt")):
        rel = txt_path.relative_to(site_dir).as_posix()
        url = base_url.rstrip("/") + "/" + rel
        status, content_type, body = fetch(url)
        results.append(check_page(url, body, status, content_type))
    return results


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="llms-output", help="llms-output directory to verify")
    parser.add_argument("--report", default=None, help="Write JSON report to this path")
    parser.add_argument("--gate", type=float, default=None, help="Minimum pass rate %% to succeed")
    args = parser.parse_args(argv)

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sites = config.get("sites", {})
    output_root = Path(args.output)
    all_results = {}
    any_verified = False

    for site_type, site_cfg in sorted(sites.items()):
        base_url = site_cfg.get("base_url")
        if not base_url:
            continue  # no public deploy configured for this site -- not an error
        any_verified = True
        results = verify_site(output_root, site_type, base_url)
        passed = sum(1 for r in results if r["ok"])
        total = len(results)
        pass_rate = round(passed / total * 100.0, 1) if total else 100.0
        all_results[site_type] = {"total": total, "passed": passed, "pass_rate": pass_rate, "pages": results}
        print(f"{site_type}: {passed}/{total} ({pass_rate}%)")

    if not any_verified:
        print("No site has a base_url configured in config.yaml -- nothing to verify "
              "(this is expected for sites with no public deploy).", file=sys.stderr)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")

    if args.gate is None or not any_verified:
        return 0

    all_ok = all(r["pass_rate"] >= args.gate for r in all_results.values())
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
