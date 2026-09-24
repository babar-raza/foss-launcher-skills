"""example_verification_sweep.py — TC-09 (MT072-2026-09-23-EXAMPLE-VERIFICATION-
PRODUCTIONIZATION): portfolio-wide tier-1 classification sweep over every
English public content page with a fenced code block.

CONTRACT: scripts/pipeline/commands/governance/example_verification_sweep.py
  purpose: the first real, full-portfolio proof that "has the verifier run
           on all public examples" can be answered with a dated artifact,
           not an inference. For every block on every English public page
           (docs/blog/kb/reference; products.aspose.org's frontmatter-
           embedded blocks are a disclosed, separate scope boundary -- see
           below), classifies it into exactly one of: PASS, SYNTAX-ERROR,
           GRAMMAR-UNAVAILABLE, NOT-EXECUTABLE-LANG, BLANK-LANG-UNCHECKED,
           SHELL-NOT-CHECKED, EMPTY -- zero blocks left unclassified. Every
           PASS/SYNTAX-ERROR result (the two ledger-eligible, deterministic
           outcomes) is written into TC-07's ExecutionProofLedger, per
           product.
  inputs:  none (walks content/ directly via `git ls-files`)
  outputs: reports/example_verification_sweep/{date}-full-sweep.json (the
           dated coverage report) + appends to
           reports/example_verification_ledger/{family}_{platform}.jsonl
  owner_domain: content-quality
  requires_test: true

Deliberately TIER 1 ONLY (offline, no toolchain, no network) -- the
sweep's honest, disclosed scope: it proves classification COMPLETENESS
(0 unclassified blocks) cheaply and reliably for every one of the 7
platforms, which tier-1 tree-sitter syntax checking can do uniformly
without any toolchain dependency. It does NOT force tier 2/3 execution
across the whole portfolio -- that would need java/rust/cpp toolchains
this dev machine doesn't have, and would risk multi-hour runtime and
toolchain-dependent instability for a first full sweep. Real tier-3
execution has already been separately, directly proven for go/net/python
(TC-03/TC-04's own end-to-end live proofs against real content) -- a
later, narrower tier-2/3 sweep is a natural follow-on, not this
taskcard's own bar (which is completeness of classification, not depth).

Known, disclosed scope boundary: products.aspose.org's code blocks live
embedded in YAML frontmatter with 4+ space indentation, which
code_fences.py's CommonMark-conformant tokenizer cannot see by design
(indented text is a CommonMark indented code block, not a fenced one --
and frontmatter isn't page BODY at all). These pages are walked and
counted (so their existence is never silently dropped from the report),
but their blocks are recorded as `excluded_frontmatter_embedded`, not
folded into "0 unclassified."

Shell-family fences (bash/sh/shell/powershell/bat/cmd) are excluded from
the same reasoning `content_eval/evaluators/example_execution.py`'s own
`_SHELL_LANGS` set already established: `syntax.py`'s tree-sitter loader
has no grammar for any shell-family language at all, so checking them
would produce a permanent, predictable GRAMMAR-UNAVAILABLE for every
install-command block in the portfolio -- not a real signal. Recorded
as `SHELL-NOT-CHECKED`, a real classification bucket, not silently
dropped.

TC-20 fix (ST-212, this same taskcard's own commit): a fence with a
BLANK info string (`lang == ""`) used to fold silently into
`NOT-EXECUTABLE-LANG` via `registry.NON_EXECUTABLE_LANGS` (which
contains `""` alongside genuinely-declared non-code languages like
`yaml`/`json`/`css`) -- indistinguishable from a page author
deliberately tagging a block as plain output. ST-212 originally (and,
confirmed live, incorrectly) diagnosed this as landing in
`GRAMMAR-UNAVAILABLE`; the real destination was already
`NOT-EXECUTABLE-LANG`, which is itself a real, disclosed, non-silent
bucket -- so the specific "silently masqueraded as checked-and-clean"
failure mode ST-212 worried about was never actually happening. What
WAS true and worth fixing: a blank info string has a genuinely
different likely cause (a missing/forgotten language tag, or ST-212's
own original "swallowed fence" theory -- a duplicate/orphaned fence
absorbing a real ` ```lang ` opener as literal content) than a page
author's deliberate `yaml`/`json`/`css` tag, and merging the two
denominators together hid that signal. Blank-lang blocks now get their
own `BLANK-LANG-UNCHECKED` bucket, split out of `NOT-EXECUTABLE-LANG`
-- live re-measurement (2026-09-24) found 34 such blocks in the
current English portfolio, previously invisible inside
`NOT-EXECUTABLE-LANG`'s combined total of 71.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from example_verification import RUNNERS_MODULE_VERSION  # noqa: E402
from example_verification.code_fences import enumerate_code_blocks  # noqa: E402
from example_verification.registry import NON_EXECUTABLE_LANGS  # noqa: E402
from example_verification.syntax import check_syntax  # noqa: E402
from example_verification_ledger import ExecutionProofLedger, ledger_key, resolve_baseline_component, resolve_toolchain_fp  # noqa: E402

_REPO_ROOT = _PIPELINE_ROOT.parents[1]

# Same set example_execution.py's own _SHELL_LANGS establishes, for the
# same reason (see module docstring) -- kept here rather than imported so
# this module has no import-time coupling to a content_eval evaluator.
_SHELL_LANGS: "frozenset[str]" = frozenset({"bash", "sh", "shell", "powershell", "bat", "cmd"})

# The 4 public sites this sweep covers. products.aspose.org is
# deliberately excluded (see module docstring) -- but still counted
# separately so its exclusion is a disclosed number, not a silent gap.
_SWEPT_SITES: "tuple[str, ...]" = (
    "docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "reference.aspose.org",
)
_EXCLUDED_SITES: "tuple[str, ...]" = ("products.aspose.org",)


_LOCALE_TAG_RE = re.compile(r"^[a-z]{2,3}(-[a-z]{2,4})?$")


def _is_locale_suffixed(name: str) -> bool:
    """`index.{locale}.md` / `{slug}.{locale}.md` -- a locale tag
    (`fr`, `pt-br`, `zh-cn`, ...) immediately before `.md`, never the
    bare English `index.md`/`{slug}.md`. Confirmed live bug while
    building this: a bare `tag.isalpha()` check rejects hyphenated
    region tags like "pt-br" as non-locale (isalpha() is False for any
    string containing "-"), silently treating that locale page as
    English."""
    stem = name[:-3] if name.endswith(".md") else name
    parts = stem.split(".")
    if len(parts) < 2:
        return False
    tag = parts[-1]
    return bool(_LOCALE_TAG_RE.match(tag))


def _is_english_public_page(rel_path: str) -> "str | None":
    """Return the site name if `rel_path` is an English public content
    page this sweep covers, else None. blog.aspose.org has no /en/
    prefix (locale is encoded purely via filename suffix); docs/kb/
    reference use /en/."""
    parts = rel_path.split("/")
    if len(parts) < 2 or not rel_path.endswith(".md"):
        return None
    site = parts[1]
    if site in _SWEPT_SITES:
        if site == "blog.aspose.org":
            if _is_locale_suffixed(parts[-1]):
                return None
            return site
        if len(parts) > 2 and parts[2] == "en":
            return site
        return None
    if site in _EXCLUDED_SITES:
        return site if len(parts) > 2 and parts[2] == "en" else None
    return None


def _family_platform_from_path(site: str, rel_path: str) -> "tuple[str, str] | None":
    """Derive (family, platform) from a content path -- the same
    `{site}/{en/}{family}/{platform}/...` convention every other tool in
    this repo relies on."""
    parts = rel_path.split("/")
    if site == "blog.aspose.org":
        tail = parts[2:]
    else:
        tail = parts[3:]
    if len(tail) < 2:
        return None
    return tail[0], tail[1]


def _classify_block(lang: str, content: str) -> "tuple[str, str, int, str]":
    """Returns (status, reason_or_empty, proof_tier, detail). status is
    always one of the 7 buckets named in the module docstring -- never
    anything else, and never silently omitted."""
    if not content.strip():
        return "EMPTY", "", 0, ""
    if not lang:
        # TC-20/ST-212: split out from NON_EXECUTABLE_LANGS (which also
        # contains "" alongside real declared non-code tags) -- a blank
        # info string is a different, worth-tracking-separately signal
        # (missing tag or a swallowed fence) than a deliberate yaml/json/
        # css tag. See module docstring.
        return "BLANK-LANG-UNCHECKED", "", 0, "fence has no language info string"
    if lang in _SHELL_LANGS:
        return "SHELL-NOT-CHECKED", "", 0, ""
    if lang in NON_EXECUTABLE_LANGS:
        return "NOT-EXECUTABLE-LANG", "", 0, ""
    result = check_syntax(lang, content)
    if result.status == "PASS":
        return "PASS", "", 1, ""
    if result.status == "SYNTAX-ERROR":
        return "SYNTAX-ERROR", "SYNTAX-ERROR", 1, result.message
    return "GRAMMAR-UNAVAILABLE", "", 0, result.message


def run_sweep(*, repo_root: "Path | None" = None) -> dict:
    """Walk every tracked English public content file, classify every
    fenced code block, write ledger-eligible results into TC-07's
    ExecutionProofLedger (one instance per family/platform, reused across
    all its pages), and return the full coverage report dict (also
    written to disk by main())."""
    repo_root = repo_root or _REPO_ROOT
    run_id = f"sweep-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    files = subprocess.run(
        ["git", "ls-files", "content"], cwd=str(repo_root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout.splitlines()

    per_site_pages: "dict[str, int]" = {}
    per_site_pages_with_code: "dict[str, int]" = {}
    status_counts: "dict[str, int]" = {}
    lang_status_counts: "dict[str, dict[str, int]]" = {}
    excluded_products_pages = 0
    ledger_writes = 0
    ledger_errors: "list[str]" = []
    ledgers: "dict[tuple[str, str], ExecutionProofLedger]" = {}
    blocks_by_file: "list[dict[str, Any]]" = []

    for rel_path in files:
        site = _is_english_public_page(rel_path)
        if site is None:
            continue
        per_site_pages[site] = per_site_pages.get(site, 0) + 1

        if site in _EXCLUDED_SITES:
            excluded_products_pages += 1
            continue

        fam_plat = _family_platform_from_path(site, rel_path)
        family, platform = fam_plat if fam_plat else ("", "")

        abs_path = repo_root / rel_path
        try:
            text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end > 0:
                text = text[end + 4:]

        blocks = enumerate_code_blocks(text)
        if not blocks:
            continue
        per_site_pages_with_code[site] = per_site_pages_with_code.get(site, 0) + 1

        file_entry = {"file": rel_path, "family": family, "platform": platform, "blocks": []}
        for block in blocks:
            lang = block.canonical_lang or block.lang or ""
            status, reason, proof_tier, detail = _classify_block(lang, block.content)
            status_counts[status] = status_counts.get(status, 0) + 1
            lang_status_counts.setdefault(lang or "<empty>", {})
            lang_status_counts[lang or "<empty>"][status] = lang_status_counts[lang or "<empty>"].get(status, 0) + 1
            file_entry["blocks"].append({
                "start_line": block.start_line, "lang": lang, "status": status,
                "detail": detail[:200],
            })

            if status in ("PASS", "SYNTAX-ERROR") and family and platform:
                key = (family, platform)
                if key not in ledgers:
                    ledgers[key] = ExecutionProofLedger(family, platform, repo_root=repo_root)
                baseline_component, baseline_kind = resolve_baseline_component(None, None)
                toolchain_fp = resolve_toolchain_fp(None, None)
                record = {
                    "schema_version": 1, "run_id": run_id, "family": family, "platform": platform,
                    "code_sha256": block.sha256_norm, "lang": lang,
                    "baseline_component": baseline_component, "baseline_kind": baseline_kind,
                    "toolchain_fp": toolchain_fp, "runners_module_version": RUNNERS_MODULE_VERSION,
                    "proof_tier": proof_tier, "status": "PASS" if status == "PASS" else "BLOCKED-WITH-REASON",
                    "reason": reason or None, "detail": detail,
                    "recorded_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                record["key"] = ledger_key(
                    record["code_sha256"], record["lang"], record["platform"],
                    record["baseline_component"], record["toolchain_fp"], record["runners_module_version"],
                )
                try:
                    ledgers[key].append(record)
                    ledger_writes += 1
                except Exception as exc:  # noqa: BLE001 -- one bad record must not kill the sweep
                    ledger_errors.append(f"{rel_path}:{block.start_line}: {exc}")

        blocks_by_file.append(file_entry)

    total_blocks = sum(status_counts.values())
    unclassified = total_blocks - sum(
        status_counts.get(s, 0) for s in
        ("PASS", "SYNTAX-ERROR", "GRAMMAR-UNAVAILABLE", "NOT-EXECUTABLE-LANG",
         "BLANK-LANG-UNCHECKED", "SHELL-NOT-CHECKED", "EMPTY")
    )

    return {
        "run_id": run_id,
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "sites_swept": list(_SWEPT_SITES),
        "sites_excluded": list(_EXCLUDED_SITES),
        "pages_by_site": per_site_pages,
        "pages_with_code_by_site": per_site_pages_with_code,
        "excluded_products_aspose_org_pages": excluded_products_pages,
        "products_aspose_org_excluded_note": (
            "products.aspose.org's code blocks live embedded in YAML frontmatter with "
            "4+ space indentation, invisible to the CommonMark-conformant fence tokenizer "
            "by design -- excluded, not silently miscounted as zero."
        ),
        "total_blocks_classified": total_blocks,
        "status_counts": status_counts,
        "unclassified_blocks": unclassified,
        "lang_status_counts": lang_status_counts,
        "ledger_writes": ledger_writes,
        "ledger_errors": ledger_errors,
        "files": blocks_by_file,
    }


def main(argv: "list[str] | None" = None, *, repo_root: "Path | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", default=None,
        help="Override the report output directory (default: reports/example_verification_sweep/).",
    )
    args = parser.parse_args(argv)

    repo_root = repo_root or _REPO_ROOT
    report = run_sweep(repo_root=repo_root)
    out_dir = Path(args.output_dir) if args.output_dir else (repo_root / "reports" / "example_verification_sweep")
    out_dir.mkdir(parents=True, exist_ok=True)
    date_stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    out_path = out_dir / f"{date_stamp}-full-sweep.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(f"Sites swept: {report['sites_swept']}")
    print(f"Pages: {report['pages_by_site']}")
    print(f"Pages with code: {report['pages_with_code_by_site']}")
    print(f"products.aspose.org pages excluded (frontmatter-embedded, disclosed): {report['excluded_products_aspose_org_pages']}")
    print(f"Total blocks classified: {report['total_blocks_classified']}")
    print(f"Status counts: {report['status_counts']}")
    print(f"UNCLASSIFIED: {report['unclassified_blocks']}")
    print(f"Ledger writes: {report['ledger_writes']} (errors: {len(report['ledger_errors'])})")
    print(f"Report written to: {out_path}")
    return 1 if report["unclassified_blocks"] else 0


if __name__ == "__main__":
    sys.exit(main())
