"""
verify_claim_accuracy.py — TC-11: Post-rewrite claim accuracy scanner.

Checks updated content sections for capability assertions that reference API
names or format names not present in the authoritative knowledge artifacts
(claims.json, formats.json, api_surface.json).

Output: WARNING only. Graduates to FAIL after calibrating false-positive rate
across 3 products (per plan).

Called by:
  - body_refresh.py after each file write (Category C updates)
  - feature_list_extender.py after bullet insert

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.ops.verify_claim_accuracy \\
        --family pdf --platform net \\
        --section "The Document class now supports WebP export." \\
        --repo-root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Globals / configure() seam ─────────────────────────────────────────────

_cfg_repo_root: Path | None = None


def configure(*, repo_root: Path | None = None) -> None:
    """Override defaults for testing."""
    global _cfg_repo_root
    _cfg_repo_root = repo_root


def _get_repo_root() -> Path:
    if _cfg_repo_root is not None:
        return _cfg_repo_root
    return Path(__file__).resolve().parents[3]


# ── Capability verbs (indicate a factual claim about behaviour) ────────────

_CAPABILITY_VERBS: frozenset[str] = frozenset({
    "supports", "support", "supported",
    "converts", "convert", "converted",
    "exports", "export", "exported",
    "imports", "import", "imported",
    "generates", "generate", "generated",
    "renders", "render", "rendered",
    "handles", "handle", "handled",
    "processes", "process", "processed",
    "reads", "read",
    "writes", "write",
    "loads", "load",
    "saves", "save",
    "creates", "create", "created",
    "parses", "parse", "parsed",
})

# Patterns that look like API/class names (CamelCase or dotted names)
_API_NAME_RE = re.compile(
    r'\b([A-Z][a-z]+[A-Z]\w*|[A-Z]{2,}\w*|(?:[A-Za-z]+\.){1,3}[A-Z]\w*)\b'
)

# Format name candidates (2-5 upper-case chars or common 3-5 char extensions)
_FORMAT_RE = re.compile(
    r'\b([A-Z]{2,5}|pdf|docx|xlsx|pptx|html|json|xml|csv|png|jpg|jpeg|svg|webp|'
    r'tiff|bmp|gif|txt|rtf|odt|ods|odp|epub|mobi)\b',
    re.IGNORECASE,
)


# ── Knowledge loaders ──────────────────────────────────────────────────────

def _load_json_safe(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_known_api_names(family: str, platform: str) -> frozenset[str]:
    """Return class/method names from api_surface.json."""
    root = _get_repo_root()
    surface_path = root / "knowledge" / family / platform / "merged" / "api_surface.json"
    data = _load_json_safe(surface_path)
    if not data:
        return frozenset()
    names: set[str] = set()
    entries = data if isinstance(data, list) else data.get("classes", [])
    for entry in entries:
        if isinstance(entry, dict):
            if "class_name" in entry:
                names.add(entry["class_name"])
            for m in entry.get("methods", []):
                if isinstance(m, dict) and "name" in m:
                    names.add(m["name"])
    return frozenset(names)


def _load_known_format_names(family: str, platform: str) -> frozenset[str]:
    """Return format names (upper-case) from formats.json."""
    root = _get_repo_root()
    fmt_path = root / "knowledge" / family / platform / "merged" / "formats.json"
    data = _load_json_safe(fmt_path)
    if not data:
        return frozenset()
    fmts = data if isinstance(data, list) else data.get("formats", [])
    names: set[str] = set()
    for f in fmts:
        if isinstance(f, dict):
            n = f.get("name") or f.get("extension") or ""
            if n:
                names.add(n.upper())
    return frozenset(names)


def _load_known_claim_symbols(family: str, platform: str) -> frozenset[str]:
    """Return API symbols referenced in claims.json."""
    root = _get_repo_root()
    claims_path = root / "knowledge" / family / platform / "merged" / "claims.json"
    data = _load_json_safe(claims_path)
    if not data:
        return frozenset()
    claims = data if isinstance(data, list) else data.get("claims", [])
    symbols: set[str] = set()
    for c in claims:
        if isinstance(c, dict):
            sym = c.get("api_member") or c.get("symbol") or ""
            if sym:
                symbols.add(sym)
    return frozenset(symbols)


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class ClaimAccuracyResult:
    verdict: str                      # "PASS" or "WARNING"
    findings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.verdict == "PASS"


# ── Core check ─────────────────────────────────────────────────────────────

def check(
    section_text: str,
    family: str,
    platform: str,
    *,
    known_api_names: frozenset[str] | None = None,
    known_format_names: frozenset[str] | None = None,
    known_claim_symbols: frozenset[str] | None = None,
) -> ClaimAccuracyResult:
    """
    Check a rewritten section for unverified capability claims.

    A finding is raised when:
      capability_verb  +  specific_name  AND  specific_name NOT in knowledge

    Only raises WARNING (never FAIL at this calibration stage).
    """
    findings: list[str] = []

    # Load knowledge if not provided (allows test injection)
    if known_api_names is None:
        known_api_names = _load_known_api_names(family, platform)
    if known_format_names is None:
        known_format_names = _load_known_format_names(family, platform)
    if known_claim_symbols is None:
        known_claim_symbols = _load_known_claim_symbols(family, platform)

    all_known: frozenset[str] = known_api_names | known_format_names | known_claim_symbols

    # Strip code blocks — only check prose
    prose = re.sub(r"```[\s\S]*?```", "", section_text)
    prose = re.sub(r"~~~[\s\S]*?~~~", "", prose)

    words = prose.split()
    # Slide a window: (verb, name) pairs
    for i, word in enumerate(words):
        stem = word.lower().rstrip(".,;:")
        if stem not in _CAPABILITY_VERBS:
            continue
        # Look ahead up to 8 words for an API/format candidate
        window = " ".join(words[i + 1 : i + 9])
        api_hits = _API_NAME_RE.findall(window)
        fmt_hits = _FORMAT_RE.findall(window)
        candidates = set(api_hits) | {h.upper() for h in fmt_hits}
        for cand in candidates:
            if len(cand) <= 1:
                continue
            # Only flag if knowledge is non-empty (avoid false positives on
            # products where knowledge artifacts are absent)
            if not all_known:
                continue
            cand_upper = cand.upper()
            if (
                cand not in all_known
                and cand_upper not in all_known
                and cand_upper not in known_format_names
            ):
                findings.append(
                    f"UNVERIFIED_CLAIM: '{stem} ... {cand}' — "
                    f"'{cand}' not found in knowledge artifacts for {family}/{platform}"
                )

    # Deduplicate (same (verb, name) pair may appear multiple times)
    findings = list(dict.fromkeys(findings))

    verdict = "WARNING" if findings else "PASS"
    return ClaimAccuracyResult(verdict=verdict, findings=findings)


# ── CLI ────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="verify_claim_accuracy — WARNING only (calibration phase)."
    )
    p.add_argument("--family", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--section", required=True, help="Section text to check.")
    p.add_argument("--repo-root", default=None, help="Repo root override.")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.repo_root:
        configure(repo_root=Path(args.repo_root))
    result = check(args.section, args.family, args.platform)
    if args.quiet:
        print(result.verdict)
    else:
        print(f"Verdict: {result.verdict}")
        for f in result.findings:
            print(f"  WARN: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
