#!/usr/bin/env python3
"""Translation-regression gate (TC-W3H-006, wave-3 incident).

Blocks commits that REGRESS a translated locale page back to English or
inject translation-prompt text — the two silently-parseable corruption
classes the wave-3 locale refresh produced (2,372 English descriptions and
prompt-leak frontmatter shipped to main with valid YAML; repaired in
2bbaa64fb5).

Rules (per staged non-English content/*.md file):
  R1 (FAIL) — staged description looks English while the HEAD version's
              description does not (translation regression)
  R2 (FAIL) — staged content contains a known translation-prompt leak phrase
  R3 (FAIL) — staged body has FEWER code-fence lines than the HEAD version
              (wave-3 fence-stripping; added 2026-07-14 after the pilot
              negative-control showed fence-only damage passed all gates).
              Not flagged when the reduction is a clean fence-pair-for-
              shortcode substitution, or (ST-153, 2026-08-31) when the
              staged page's own fence count is still >= its English
              counterpart's current fence count -- i.e. the locale page is
              catching up to a removal that already happened on English,
              not introducing new divergence.

The check compares the STAGED blob against HEAD, so it only fires on commits
that make a translated field worse — pre-existing English descriptions
(1,636 tracked in backlog ST-012) do not block unrelated commits.

Usage — staged mode (pre-commit):
    check_translation_regression.py --staged FILE [FILE ...]

Usage — ref mode (CI over a PR diff):
    check_translation_regression.py --base origin/main FILE [FILE ...]
    (compares HEAD:file against BASE:file)

Exit codes:
    0 — all pass
    1 — at least one FAIL
    2 — usage error
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

import yaml

NONLATIN_LOCALES = {"ar", "bg", "el", "fa", "he", "hi", "ja", "ko", "ru", "sr", "th", "uk", "zh"}
EN_STOPWORDS = [" the ", " and ", " with ", " for ", " how to ", " using ", " from ", " your ", " all "]
LEAK_RE = re.compile(
    r"SÓLO la traducción|ONLY the translation|Preservar todo el formato|"
    r"Preserve all formatting|shortcodes de Hugo exactamente|Hugo shortcodes exactly|"
    r"No explicaciones, notas ni comentarios|Do not add, remove, or reorder content"
)


def _split_fm(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else None


def _description(text: str) -> str | None:
    fm = _split_fm(text)
    if fm is None:
        return None
    try:
        data = yaml.safe_load(fm)
    except yaml.YAMLError:
        return None  # unparseable frontmatter is check_frontmatter_yaml's job
    if isinstance(data, dict):
        value = data.get("description")
        return value if isinstance(value, str) else None
    return None


def _ascii_alpha_frac(s: str) -> float:
    alpha = [c for c in s if c.isalpha()]
    if len(alpha) < 20:
        return 0.0
    return sum(1 for c in alpha if c.isascii()) / len(alpha)


def looks_english(text: str | None, locale: str) -> bool:
    """Heuristic: does this description read as English for the given locale?"""
    if not text or locale == "en":
        return False
    if locale in NONLATIN_LOCALES:
        return _ascii_alpha_frac(text) > 0.7
    low = f" {text.lower()} "
    return sum(1 for w in EN_STOPWORDS if w in low) >= 4


def locale_of(path: str) -> str:
    """content/<site>/<locale>/... -> locale (or 'en' if shape is unexpected)."""
    parts = path.replace("\\", "/").split("/")
    return parts[2] if len(parts) > 2 and parts[0] == "content" else "en"


def english_counterpart_path(path: str) -> str | None:
    """content/<site>/<locale>/<rest> -> content/<site>/en/<rest>, or None
    when `path` doesn't have the expected shape or is already English."""
    parts = path.replace("\\", "/").split("/")
    if len(parts) > 2 and parts[0] == "content" and parts[2] != "en":
        parts = list(parts)
        parts[2] = "en"
        return "/".join(parts)
    return None


def _fence_count(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.lstrip().startswith("```"))


# Shortcodes known to legitimately replace a whole fenced code block (open
# fence + content + close fence) with a single line, e.g. Mission MT008's
# maven-coord/maven-gav (plans/master-plan.md D-02). A newly-introduced call
# to one of these is a specific, hard-to-accidentally-produce signal of an
# intentional structural substitution -- unlike wave-3 fence-stripping, which
# leaves the original code CONTENT behind as orphaned text with no new,
# validly-argumented shortcode syntax in its place.
_BLOCK_REPLACING_SHORTCODE_RE = re.compile(r"\{\{<\s*maven-(?:coord|gav)\s")


def _shortcode_call_count(text: str) -> int:
    return len(_BLOCK_REPLACING_SHORTCODE_RE.findall(text))


def check_pair(
    cur_text: str,
    old_text: str | None,
    locale: str,
    *,
    english_fence_count: int | None = None,
) -> list[str]:
    """Pure core: return failure codes for one (current, previous) pair.

    `english_fence_count` (ST-153) is the CURRENT fence count of this page's
    English counterpart, when available -- see its use in R3 below.
    """
    failures = []
    if LEAK_RE.search(cur_text):
        failures.append("R2")
    cur_desc = _description(cur_text)
    if looks_english(cur_desc, locale):
        old_desc = _description(old_text) if old_text else None
        # Only a REGRESSION blocks: previous version had a non-English desc.
        if old_desc and not looks_english(old_desc, locale):
            failures.append("R1")
    if old_text:
        fence_reduction = _fence_count(old_text) - _fence_count(cur_text)
        if fence_reduction > 0:
            # A clean block-for-shortcode substitution removes whole fence
            # PAIRS (open + close = 2 markers) and adds 1 shortcode call per
            # pair. An ODD reduction can never be explained this way -- it is
            # exactly the wave-3 signature (one marker of a pair stripped,
            # content left orphaned) -- so it always fails, regardless of
            # shortcode count.
            new_shortcode_calls = _shortcode_call_count(cur_text) - _shortcode_call_count(old_text)
            shortcode_substitution = not (
                fence_reduction % 2 != 0 or new_shortcode_calls < fence_reduction // 2
            )
            # ST-153: a staged locale body can also legitimately be catching
            # up to a fence removal that ALREADY happened on the English
            # source (e.g. an upstream API's example was deleted from
            # English first, and a later locale patch just propagates that
            # same removal) -- not a new divergence introduced here. Confirmed
            # live 2026-08-31 (MT040 Phase I): an Arabic page correctly
            # received a "<!-- Example removed -->" marker that was already
            # present, unchanged, in the current English source. Only
            # suppress when the locale's OWN post-edit fence count is not
            # BELOW the English counterpart's OWN current fence count -- i.e.
            # this locale page is not left any further out of structural sync
            # with English than English's own current state already is. A
            # locale that starts out below English's fence count and drops
            # further still fails, same as before.
            caught_up_to_english = (
                english_fence_count is not None
                and _fence_count(cur_text) >= english_fence_count
            )
            if not shortcode_substitution and not caught_up_to_english:
                failures.append("R3")
    return failures


def _git_show(ref: str) -> str | None:
    result = subprocess.run(["git", "show", ref], capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Translation-regression gate")
    parser.add_argument("files", nargs="*", help="content .md files to check")
    parser.add_argument("--staged", action="store_true",
                        help="compare staged blob (:0:file) against HEAD:file")
    parser.add_argument("--base", default=None,
                        help="compare HEAD:file against BASE:file (CI mode)")
    args = parser.parse_args()

    if not args.files:
        parser.print_usage(sys.stderr)
        return 2
    if not args.staged and not args.base:
        print("ERROR: pass --staged or --base <ref>", file=sys.stderr)
        return 2

    fail_count = 0
    for f in args.files:
        path = f.replace("\\", "/")
        if not path.endswith(".md") or not path.startswith("content/"):
            continue
        locale = locale_of(path)
        if locale == "en":
            continue
        if args.staged:
            cur = _git_show(f":0:{path}")
            old = _git_show(f"HEAD:{path}")
        else:
            cur = _git_show(f"HEAD:{path}")
            old = _git_show(f"{args.base}:{path}")
        if cur is None:
            continue  # deleted / not in this diff side

        english_fence_count = None
        english_path = english_counterpart_path(path)
        if english_path:
            english_ref = f":0:{english_path}" if args.staged else f"HEAD:{english_path}"
            english_text = _git_show(english_ref)
            if english_text is not None:
                english_fence_count = _fence_count(english_text)

        for code in check_pair(cur, old, locale, english_fence_count=english_fence_count):
            fail_count += 1
            if code == "R1":
                print(f"R1 FAIL {path}: description regressed to English "
                      f"(previous version was translated, locale '{locale}')")
            elif code == "R2":
                print(f"R2 FAIL {path}: translation-prompt leak phrase found")
            else:
                print(f"R3 FAIL {path}: staged version has fewer code-fence "
                      f"lines than the previous version (fence stripping)")

    if fail_count:
        print(f"\ncheck_translation_regression: {fail_count} FAIL(s)")
        return 1
    print("check_translation_regression: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
