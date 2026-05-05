"""CI helper: parse audit JSON output and exit 1 if any FAILs are present.

Replaces the fragile inline Python in content-audit.yml.

Usage:
    python scripts/pipeline/check_audit_results.py audit-results.json
    python scripts/pipeline/check_audit_results.py audit-results.json --warn-as-error
"""
import json
import sys
from pathlib import Path


def main():
    args = sys.argv[1:]
    warn_as_error = "--warn-as-error" in args
    paths = [a for a in args if not a.startswith("--")]

    if not paths:
        print("Usage: check_audit_results.py <audit-results.json> [--warn-as-error]",
              file=sys.stderr)
        sys.exit(2)

    result_path = Path(paths[0])
    if not result_path.exists():
        print(f"ERROR: audit results file not found: {result_path}", file=sys.stderr)
        print("       Did audit.py fail before writing output?", file=sys.stderr)
        sys.exit(2)

    content = result_path.read_text(encoding="utf-8").strip()
    if not content:
        print("audit-results.json is empty — no files were modified; audit passes.")
        sys.exit(0)
    try:
        results = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"ERROR: malformed JSON in {result_path}: {e}", file=sys.stderr)
        sys.exit(2)

    fails = results.get("total_fails", 0)
    warns = results.get("total_warns", 0)
    products = results.get("products_checked", [])
    findings = results.get("findings", [])

    print(f"Products checked: {len(products)}")
    print(f"FAIL: {fails} | WARN: {warns}")

    if fails > 0:
        print("\nFAIL findings:")
        for f in findings:
            if f.get("level") == "FAIL":
                loc = f"{f['file']}:{f['line']}"
                msg = f['message']
                suggestion = f.get("suggestion", "")
                line = f"  {loc} — {msg}"
                if suggestion:
                    line += f" → {suggestion}"
                print(line)

    if warns > 0 and warn_as_error:
        print("\nWARN findings (--warn-as-error active):")
        for f in findings:
            if f.get("level") == "WARN":
                print(f"  {f['file']}:{f['line']} — {f['message']}")

    threshold_hit = fails > 0 or (warn_as_error and warns > 0)
    if threshold_hit:
        print("\nAudit FAILED.")
        sys.exit(1)

    print("All content passed audit.")
    sys.exit(0)


if __name__ == "__main__":
    main()
