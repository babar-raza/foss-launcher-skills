"""MT074 B20: registered, tested verdict gate for S-127 (independent-content-review).

Promoted out of the skill's inline ~60-line block so it is a tested, registered module
instead of copy-pasted shell. Pure function of three inputs under `run_dir`:

  tiers.json    -- {page: 1|2|3} tier assignment (deterministic, written by the skill)
  verdicts/*.json -- one file per reviewer verdict, written byte-for-byte by the orchestrator
  pages (list)  -- the pages this run reviewed, one per line in the pages file

A page is CLEARED only when, bound to its CURRENT content sha256 (LF-normalised bytes), it
has the required number of valid PASS verdicts from distinct reviewers who are not authors,
and no FAIL verdict or blocker/major finding exists at that hash. A verdict for any earlier
hash is ignored (an edit after review invalidates it). Any blocker overrides every PASS.
There is no way to clear a finding except a changed page and a fresh review.

This module never edits a reviewed page, a verdict file, or any content/knowledge file.
It only reads `tiers.json` and `verdicts/*.json` and writes `gate.json`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DIMS = ("R1", "R2", "R3", "R4", "R5", "R6")
REQUIRED_KEYS = ("page", "content_sha256", "reviewer_id", "tier", "checks", "findings", "verdict")


def sha256_lf(path: Path) -> str:
    """LF-normalised content hash -- matches the hash a verdict was bound to."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_verdict(v: dict, authors: set[str]) -> tuple[bool, str]:
    """Structural + policy validation of one parsed verdict. Returns (ok, reason-if-not)."""
    for k in REQUIRED_KEYS:
        if k not in v:
            return False, f"missing key {k}"
    if v["reviewer_id"] in authors:
        return False, "reviewer is an author"
    if v["verdict"] == "PASS":
        if any(f.get("severity") in ("blocker", "major") for f in v["findings"]):
            return False, "PASS with blocker/major finding"
        if any(c.get("result") not in ("PASS", "NA") for c in v["checks"]):
            return False, "PASS with a failed check"
        if any(c.get("result") == "NA" and not str(c.get("note", "")).strip() for c in v["checks"]):
            return False, "NA without a note"
        seen = {str(c.get("id", ""))[:2] for c in v["checks"]}
        missing = [d for d in DIMS if d not in seen]
        if missing:
            return False, "dimension missing: " + ",".join(missing)
    return True, ""


def load_verdicts(run_dir: Path) -> dict[str, list[tuple[str, dict]]]:
    out: dict[str, list[tuple[str, dict]]] = {}
    verdicts_dir = run_dir / "verdicts"
    if not verdicts_dir.is_dir():
        return out
    for f in sorted(verdicts_dir.glob("*.json")):
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(v, dict) or "page" not in v:
            continue
        out.setdefault(v["page"], []).append((f.name, v))
    return out


def run_gate(run_dir: Path, pages: list[str], authors: set[str]) -> dict:
    """Pure gate evaluation. `pages` is the exact ordered list from the pages file
    (blank lines and '#' comments already stripped by the caller)."""
    tiers_path = run_dir / "tiers.json"
    tiers = json.loads(tiers_path.read_text(encoding="utf-8")) if tiers_path.is_file() else {}
    verdicts_by_page = load_verdicts(run_dir)

    report: list[dict] = []
    cleared: list[str] = []
    for page in pages:
        need = 2 if int(tiers.get(page, 1)) == 1 else 1
        page_path = Path(page)
        cur = sha256_lf(page_path) if page_path.is_file() else None
        row = {"page": page, "tier": tiers.get(page, 1), "need": need, "sha256": cur,
               "status": "", "why": []}
        passes: dict[str, str] = {}
        blocked = False
        for name, v in verdicts_by_page.get(page, []):
            if v.get("content_sha256") != cur:
                row["why"].append(f"{name}: stale hash (ignored)")
                continue
            good, why = validate_verdict(v, authors)
            if not good:
                row["why"].append(f"{name}: invalid ({why})")
            if v.get("verdict") == "FAIL" or any(
                f.get("severity") == "blocker" for f in v.get("findings", [])
            ):
                blocked = True
                row["why"].append(f"{name}: FAIL or blocker at current hash")
            elif good:
                passes[v["reviewer_id"]] = name

        if cur is None:
            row["status"] = "MISSING_PAGE"
        elif blocked:
            row["status"] = "REWORK_REQUIRED"
        elif len(passes) >= need:
            row["status"] = "CLEARED"
            cleared.append(page)
        else:
            row["status"] = "NEEDS_REVIEW"
            row["why"].append(f"{len(passes)}/{need} independent PASS verdicts at current hash")
        report.append(row)

    return {"pages": report, "cleared": cleared, "all_cleared": len(cleared) == len(pages)}


def _read_pages(pages_file: Path) -> list[str]:
    return [
        p.strip()
        for p in pages_file.read_text(encoding="utf-8").splitlines()
        if p.strip() and not p.strip().startswith("#")
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=Path, help="the S-127 run directory ($RUN)")
    ap.add_argument("pages_file", type=Path, help="newline-delimited list of reviewed page paths")
    ap.add_argument("authors", nargs="?", default="",
                     help="comma-separated author reviewer-ids (none may count toward PASS)")
    args = ap.parse_args(argv)

    authors = {a for a in args.authors.split(",") if a}
    pages = _read_pages(args.pages_file)
    out = run_gate(args.run_dir, pages, authors)

    (args.run_dir / "gate.json").write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    for r in out["pages"]:
        print(f"{r['status']:16} tier{r['tier']} {r['page']}  {'; '.join(r['why'])}")
    print("ALL_CLEARED" if out["all_cleared"] else "NOT_CLEARED")
    return 0 if out["all_cleared"] else 1


if __name__ == "__main__":
    sys.exit(main())
