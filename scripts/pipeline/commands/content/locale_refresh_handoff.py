"""
locale_refresh_handoff.py — S-107: After body updates, identify locale equivalents
requiring re-translation and queue them for the appropriate translation skill.

Rules:
  changes < 3 sentences, topology matches English → queue for S-75 (locale-patch)
  changes >= 3 sentences, topology matches English → queue for S-HT-01 (ht-translate)
  locale H2 topology does not match English (RG-004 mismatch) → queue for S-HT-01
  (ht-translate) as STRUCTURAL_DRIFT, regardless of text-diff size — a removed or
  restructured section has no literal text for S-75 to patch against, and S-75's own
  documented safety rules refuse locale files that have diverged structurally.

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.locale_refresh_handoff \\
        pdf net --receipts reports/refresh_review/pdf/net/receipts/

Output:
    reports/refresh_review/{family}/{platform}/locale_handoff.yaml

Output schema:
    locale_handoff:
      - source_page: ...
        source_revision: ...
        changed_sections: [...]
        locales_requiring_update:
          - locale: ar
            path: content/docs.aspose.org/ar/pdf/net/...
            handoff_status: QUEUED
            translate_skill: S-75
          - locale: es
            path: content/docs.aspose.org/es/pdf/net/...
            handoff_status: STRUCTURAL_DRIFT
            translate_skill: S-HT-01
            topology_detail: "source has 4 H2(s), locale has 3 H2(s)"
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import glob
import re
import yaml
from typing import Any

from commands.ops.check_locale_topology import check_locale as _check_h2_topology

# ── Constants ──────────────────────────────────────────────────────────────

SKILL_SMALL = "S-75"   # locale-patch (< 3 sentences changed)
# ht-translate, single-page retranslation (>= 3 sentences changed) — NOT
# S-HT-02/batch: directory-scoped with a recursive copy-back that risks
# overwriting unrelated locale files. This routes one locale's copy of one
# page, never a whole directory, so the single-page tool is the right shape.
SKILL_LARGE = "S-HT-01"
# Locale H2 topology doesn't match English (RG-004 mismatch) — always
# re-translate, never patch: S-75 is documented unsafe for section-level drift.
SKILL_STRUCTURAL = "S-HT-01"

SMALL_CHANGE_THRESHOLD = 3  # sentences

# Known locale codes supported in content/
# Note: "sl" is stale for most subdomains (no populated content/*/sl/ dir
# outside a near-empty docs.aspose.org/sl/) but is left as-is — removing it
# is a separate, unscoped decision (see backlog ST-151/ST-152 notes).
KNOWN_LOCALES = [
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms", "nl",
    "no", "pl", "pt", "ro", "ru", "sk", "sl", "sr", "sv", "th", "tr",
    "uk", "vi", "zh",
]

# ── Configurable defaults ──────────────────────────────────────────────────

_cfg_reports_root: str = "reports/refresh_review"
_cfg_content_root: str = "content"


def configure(
    reports_root: str | None = None,
    content_root: str | None = None,
) -> None:
    global _cfg_reports_root, _cfg_content_root
    if reports_root is not None:
        _cfg_reports_root = reports_root
    if content_root is not None:
        _cfg_content_root = content_root


# ── Loaders ────────────────────────────────────────────────────────────────

def _load_receipts(receipts_dir: str) -> list[dict]:
    """Load all content_refresh_receipt YAML files from receipts_dir."""
    receipts: list[dict] = []
    for f in Path(receipts_dir).glob("*.yaml"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict) and "content_refresh_receipt" in data:
                r = data["content_refresh_receipt"]
                if r.get("verdict") == "BODY_UPDATED":
                    receipts.append(r)
        except Exception:
            continue
    return receipts


# ── Locale discovery ───────────────────────────────────────────────────────

def _find_locale_equivalents(
    en_page_path: str,
    family: str,
    platform: str,
) -> list[tuple[str, str]]:
    """
    Given an en page path, find locale equivalents for all known locales.
    Returns list of (locale, locale_page_path) tuples for existing files.

    Handles two path patterns:
      docs/kb: content/{subdomain}/en/{family}/{platform}/... → ./{locale}/...
      blog:    content/blog.aspose.org/{family}/{platform}/... (no locale dir)
    """
    en_path = Path(en_page_path)
    results: list[tuple[str, str]] = []

    # Normalise path separators
    path_str = en_page_path.replace("\\", "/")

    # Pattern: content/{subdomain}/en/{family}/{platform}/...
    m = re.match(
        r"(content/[^/]+)/en/(" + re.escape(family) + r"/" + re.escape(platform) + r"/.*)",
        path_str,
    )
    if not m:
        return results

    subdomain_root = m.group(1)
    rest = m.group(2)  # {family}/{platform}/...

    for locale in KNOWN_LOCALES:
        candidate = f"{subdomain_root}/{locale}/{rest}"
        if Path(candidate).exists():
            results.append((locale, candidate))

    return results


# ── Change-size classification ─────────────────────────────────────────────

def _count_changed_sentences(receipt: dict) -> int:
    """Estimate number of sentences changed based on sections_changed count."""
    sections = receipt.get("body_sections_changed", [])
    # Rough heuristic: each section averages ~2.5 sentences
    return max(len(sections) * 2, 1)


def _classify_change_size(receipt: dict) -> str:
    """Return 'small' or 'large' based on estimated sentence count."""
    count = _count_changed_sentences(receipt)
    return "small" if count < SMALL_CHANGE_THRESHOLD else "large"


# ── Build handoff entries ──────────────────────────────────────────────────

def _build_handoff_entry(
    receipt: dict,
    locale_paths: list[tuple[str, str]],
) -> dict:
    """Build a locale_handoff entry for one source page."""
    size = _classify_change_size(receipt)
    translate_skill = SKILL_SMALL if size == "small" else SKILL_LARGE
    source_page = receipt.get("page_path", "")

    locales_requiring_update: list[dict] = []
    for locale, locale_path in locale_paths:
        mismatch = None
        if source_page:
            mismatch = _check_h2_topology(Path(source_page), Path(locale_path))

        if mismatch is not None:
            locales_requiring_update.append(
                {
                    "locale": locale,
                    "path": locale_path,
                    "handoff_status": "STRUCTURAL_DRIFT",
                    "translate_skill": SKILL_STRUCTURAL,
                    "change_size": size,
                    "topology_detail": mismatch.get("detail", ""),
                }
            )
        else:
            locales_requiring_update.append(
                {
                    "locale": locale,
                    "path": locale_path,
                    "handoff_status": "QUEUED",
                    "translate_skill": translate_skill,
                    "change_size": size,
                }
            )

    return {
        "source_page": receipt.get("page_path", ""),
        "source_revision": receipt.get("new_hash", ""),
        "changed_sections": receipt.get("body_sections_changed", []),
        "locales_requiring_update": locales_requiring_update,
    }


# ── Main run ───────────────────────────────────────────────────────────────

def run(family: str, platform: str, receipts_dir: str | None = None) -> list[dict]:
    """Main logic entry point. Returns list of handoff entries."""
    if receipts_dir is None:
        receipts_dir = str(Path(_cfg_reports_root) / family / platform / "receipts")

    receipts = _load_receipts(receipts_dir)
    handoff_entries: list[dict] = []

    for receipt in receipts:
        page_path = receipt.get("page_path", "")
        if not page_path:
            continue

        locale_paths = _find_locale_equivalents(page_path, family, platform)
        if not locale_paths:
            continue

        entry = _build_handoff_entry(receipt, locale_paths)
        handoff_entries.append(entry)

    # Write output
    out_path = Path(_cfg_reports_root) / family / platform / "locale_handoff.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump({"locale_handoff": handoff_entries}, f, default_flow_style=False, allow_unicode=True)

    return handoff_entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "locale_refresh_handoff — S-107: Identify locale equivalents requiring "
            "re-translation after body updates."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=scripts/pipeline python -m commands.content.locale_refresh_handoff \\
      pdf net --receipts reports/refresh_review/pdf/net/receipts/

Output: reports/refresh_review/{family}/{platform}/locale_handoff.yaml
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java)")
    parser.add_argument(
        "--receipts",
        default=None,
        help="Override receipts directory path",
    )
    args = parser.parse_args()

    entries = run(args.family, args.platform, receipts_dir=args.receipts)
    total_locales = sum(len(e["locales_requiring_update"]) for e in entries)
    out_path = f"reports/refresh_review/{args.family}/{args.platform}/locale_handoff.yaml"
    print(f"locale_refresh_handoff: {args.family}/{args.platform}")
    print(f"  source pages queued : {len(entries)}")
    print(f"  locale updates total: {total_locales}")
    print(f"  output              : {out_path}")


if __name__ == "__main__":
    main()
