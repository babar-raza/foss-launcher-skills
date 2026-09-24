"""locale_code_block_equivalence.py — TC-14 (MT072-2026-09-23-EXAMPLE-
VERIFICATION-PRODUCTIONIZATION): bounded locale-equivalence gate for code
blocks.

CONTRACT: scripts/pipeline/commands/governance/locale_code_block_equivalence.py
  purpose: assert every locale variant's fenced code block is byte-equal
           (normalized) to its English counterpart at the same position on
           the same page, and flag drift -- WITHOUT re-executing anything.
           Full re-execution of the ~124k locale code blocks is explicitly
           out of scope for this taskcard (governing plan's own "Out of
           scope" section); code blocks in this repo's translated pages are
           never supposed to differ from English at all (only surrounding
           prose is translated), so any difference IS the signal, not a
           false positive to filter out.
  inputs:  none (walks content/ directly via `git ls-files`, same idiom
           TC-09's example_verification_sweep.py already established)
  outputs: reports/locale_code_block_equivalence/{date}-report.json (dated,
           full finding list) + a non-zero exit when DRIFT findings exist
           (gate mode)
  owner_domain: content-quality
  requires_test: true

Reuses lib/example_verification/code_fences.py's canonical CommonMark fence
tokenizer (RC6/RC19's "one parser" mandate, the same module TC-11 collapsed
code_syntax_check.py's own duplicate loader onto) rather than writing parser
#41 -- and its pre-computed `sha256_norm` (CRLF/line-ending/common-indent/
trailing-whitespace normalized) IS the "byte-equal (normalized)" comparison
the governing plan asks for; no separate normalization logic needed here.

Two on-disk locale-siblinghood conventions coexist in this repo (confirmed
live, see also `_is_english_public_page` in example_verification_sweep.py):
  - docs.aspose.org / kb.aspose.org / reference.aspose.org: a locale-named
    DIRECTORY parallel to `en/` (content/{site}/{locale}/{family}/
    {platform}/... mirrors content/{site}/en/{family}/{platform}/...).
  - blog.aspose.org: no locale directory at all -- the locale is a FILENAME
    suffix on a sibling in the SAME directory (index.md / index.{locale}.md).
  products.aspose.org is excluded (see below, same boundary TC-09 disclosed).

Three finding kinds, in ascending severity:
  COUNT_MISMATCH — the locale page has a different number of code blocks
                    than English. This is the wave-3-incident signature
                    (fence openers silently stripped by a translator run,
                    see memory `wave3-locale-incident`) — the highest-
                    confidence real defect this gate can find.
  LANG_MISMATCH   — same block count, but block N's fence language tag
                    differs (e.g. a locale run re-tagged or reordered
                    blocks).
  CONTENT_DRIFT   — same count, same language, but the normalized content
                    hash differs -- the code itself was altered in
                    translation.

A page with zero English code blocks is skipped entirely (nothing to
compare). A locale that doesn't exist for a given page is skipped, not
flagged (translation coverage/completeness is a different, already-tracked
concern -- this gate only checks EQUIVALENCE where a locale page exists).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from content_discovery import LOCALE_CODES  # noqa: E402
from example_verification.code_fences import CodeBlock, enumerate_code_blocks  # noqa: E402

_REPO_ROOT = _PIPELINE_ROOT.parents[1]

# Same 4 sites TC-09's sweep covers as real page-body content.
# products.aspose.org's code blocks live embedded in YAML frontmatter
# (indented, not fenced -- code_fences.py can't see them by design, same
# disclosed boundary as TC-09), so it's excluded here too.
_SWEPT_SITES: "tuple[str, ...]" = (
    "docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "reference.aspose.org",
)
_DIR_LOCALE_SITES: "tuple[str, ...]" = ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org")

_LOCALE_TAG_RE = re.compile(r"^[a-z]{2,3}(-[a-z]{2,4})?$")


def _is_locale_suffixed(name: str) -> "str | None":
    """`index.{locale}.md` -> locale tag, or None (bare English filename).
    Same hyphenated-region-tag fix example_verification_sweep.py's own
    `_is_locale_suffixed` already made (a bare `tag.isalpha()` rejects
    "pt-br")."""
    stem = name[:-3] if name.endswith(".md") else name
    parts = stem.split(".")
    if len(parts) < 2:
        return None
    tag = parts[-1]
    return tag if _LOCALE_TAG_RE.match(tag) else None


def _classify_page(site: str, rel_path: str) -> "tuple[str, str] | None":
    """Return (locale, group_key) for a content page, or None if `rel_path`
    isn't a page this gate covers. `group_key` identifies "the same page
    across locales" -- comparable pages share a group_key."""
    parts = rel_path.split("/")
    if len(parts) < 2 or not rel_path.endswith(".md"):
        return None
    if parts[1] != site:
        return None
    if site == "blog.aspose.org":
        locale = _is_locale_suffixed(parts[-1]) or "en"
        if locale == "en":
            group_key = rel_path
        else:
            suffix = f".{locale}.md"
            group_key = rel_path[: -len(suffix)] + ".md"
        return locale, group_key
    if site in _DIR_LOCALE_SITES:
        if len(parts) < 3:
            return None
        locale = parts[2]
        if locale != "en" and locale not in LOCALE_CODES:
            return None
        group_parts = list(parts)
        group_parts[2] = "en"
        return locale, "/".join(group_parts)
    return None


@dataclass(slots=True)
class DriftFinding:
    group_key: str
    en_path: str
    locale: str
    locale_path: str
    block_index: int
    kind: str  # COUNT_MISMATCH | LANG_MISMATCH | CONTENT_DRIFT
    detail: str


def _body_only(text: str) -> str:
    """Strip a leading YAML frontmatter block, same idiom
    example_verification_sweep.py's run_sweep() already uses."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            return text[end + 4:]
    return text


def _blocks_for(abs_path: Path) -> "list[CodeBlock]":
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return enumerate_code_blocks(_body_only(text))


def compare_group(repo_root: Path, group_key: str, en_rel: str, locale_rels: "dict[str, str]") -> "list[DriftFinding]":
    en_blocks = _blocks_for(repo_root / en_rel)
    if not en_blocks:
        return []
    findings: "list[DriftFinding]" = []
    for locale, locale_rel in sorted(locale_rels.items()):
        locale_blocks = _blocks_for(repo_root / locale_rel)
        if len(locale_blocks) != len(en_blocks):
            findings.append(DriftFinding(
                group_key=group_key, en_path=en_rel, locale=locale, locale_path=locale_rel,
                block_index=-1, kind="COUNT_MISMATCH",
                detail=f"english has {len(en_blocks)} code block(s), {locale} has {len(locale_blocks)}",
            ))
            continue
        for i, (eb, lb) in enumerate(zip(en_blocks, locale_blocks)):
            if eb.canonical_lang != lb.canonical_lang:
                findings.append(DriftFinding(
                    group_key=group_key, en_path=en_rel, locale=locale, locale_path=locale_rel,
                    block_index=i, kind="LANG_MISMATCH",
                    detail=f"english lang={eb.canonical_lang!r}, {locale} lang={lb.canonical_lang!r}",
                ))
            elif eb.sha256_norm != lb.sha256_norm:
                findings.append(DriftFinding(
                    group_key=group_key, en_path=en_rel, locale=locale, locale_path=locale_rel,
                    block_index=i, kind="CONTENT_DRIFT",
                    detail=f"block {i} ({eb.canonical_lang}) normalized content differs from english",
                ))
    return findings


def run_check(*, repo_root: "Path | None" = None) -> dict:
    repo_root = repo_root or _REPO_ROOT
    files = subprocess.run(
        ["git", "ls-files", "content"], cwd=str(repo_root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout.splitlines()

    # group_key -> {"en": rel_path, "locales": {locale: rel_path}}
    groups: "dict[str, dict[str, Any]]" = {}
    pages_seen = 0
    for rel_path in files:
        parts = rel_path.split("/")
        if len(parts) < 2:
            continue
        site = parts[1]
        if site not in _SWEPT_SITES:
            continue
        classified = _classify_page(site, rel_path)
        if classified is None:
            continue
        locale, group_key = classified
        pages_seen += 1
        entry = groups.setdefault(group_key, {"en": None, "locales": {}})
        if locale == "en":
            entry["en"] = rel_path
        else:
            entry["locales"][locale] = rel_path

    findings: "list[DriftFinding]" = []
    groups_with_en_code = 0
    groups_compared = 0
    for group_key, entry in sorted(groups.items()):
        en_rel = entry["en"]
        if en_rel is None or not entry["locales"]:
            continue
        en_blocks = _blocks_for(repo_root / en_rel)
        if not en_blocks:
            continue
        groups_with_en_code += 1
        groups_compared += len(entry["locales"])
        findings.extend(compare_group(repo_root, group_key, en_rel, entry["locales"]))

    kind_counts: "dict[str, int]" = {}
    for f in findings:
        kind_counts[f.kind] = kind_counts.get(f.kind, 0) + 1

    return {
        "run_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "pages_seen": pages_seen,
        "page_groups": len(groups),
        "page_groups_with_english_code": groups_with_en_code,
        "locale_page_comparisons": groups_compared,
        "finding_count": len(findings),
        "finding_kind_counts": kind_counts,
        "findings": [asdict(f) for f in findings],
    }


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--report", type=Path, help="also write the full report to this path")
    parser.add_argument("--max-print", type=int, default=50, help="max findings to print in text mode")
    parser.add_argument("--repo-root", type=Path, default=None, help="override repo root (testing)")
    args = parser.parse_args(argv)

    report = run_check(repo_root=args.repo_root)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(
            f"locale-code-block-equivalence: {report['pages_seen']} pages seen, "
            f"{report['page_groups_with_english_code']} english pages-with-code compared against "
            f"{report['locale_page_comparisons']} locale counterpart(s), "
            f"{report['finding_count']} drift finding(s) {report['finding_kind_counts']}"
        )
        for f in report["findings"][: args.max_print]:
            print(f"  [{f['kind']}] {f['en_path']} <-> {f['locale_path']} (block {f['block_index']}): {f['detail']}")
        remaining = report["finding_count"] - args.max_print
        if remaining > 0:
            print(f"  ... and {remaining} more")

    return 1 if report["finding_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
