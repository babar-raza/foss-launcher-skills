"""check_contract_claims.py — HARDEN-A9: self-documentation drift checker.

CONTRACT: scripts/ci/checks/check_contract_claims.py
  purpose: Skill markdown and registry.yaml both make claims of the shape
           "X calls/uses/invokes Y" or "X is gated on Y" about the pipeline's
           own code. Two such claims were found FALSE by direct code reading
           during the 2026-07-22 reliability audit: registry.yaml claimed
           change_guard.py calls no_downgrade_guard (it doesn't — verified by
           reading the full file), and refresh-product.md claimed S-76 is
           gated on a "manifest schema 5e" validation that commit.md never
           performs. Agents (including sessions of this very assistant) read
           these files as ground truth when planning work — a false claim
           here is not a documentation nit, it's a wrong mental model of what
           protection actually exists.
  scope, honestly: this is a HEURISTIC pattern-matcher, not a formal verifier.
           It catches claims matching its patterns and cross-references them
           against grep-detectable import/call relationships. It cannot prove
           the ABSENCE of an undocumented-but-true relationship, and it will
           miss claims phrased outside its patterns. It closes the two known
           instances and the class of future instances matching the same
           shape — not a general contract-verification system.
  patterns matched (case-insensitive), each capturing (subject, verb, object):
    "<subject> (calls|invokes|uses) <object.py|object()>"
    "<subject> is gated on <object>"
  cross-reference: for a claim "A calls/uses B.py", B (module name without
           .py) must appear as an import target somewhere in A's own source
           (`import B`, `from B import`, `from lib.B import`, `from
           commands...B import`) OR A's source must literally invoke B as a
           subprocess (`B.py` string appears in a subprocess call argument
           list). Neither found -> FINDING.
  false-positive damping: only claims about *.py filenames or bracketed
           skill/script identifiers are checked (prose like "gated on human
           review" is not a code claim and is skipped).
  finding-2 addendum (2026-07-22 remediation): a "<subject> is gated on
           <prose>" claim whose object is NOT a checkable .py filename is no
           longer silently dropped — it is now surfaced as a distinct,
           advisory-only "UNVERIFIABLE_PROSE_CLAIM" finding (kind field),
           never affecting the exit code. This is exactly the shape of the
           original refresh-product.md bug ("S-76 is gated on manifest
           validation == PASS (schema 5e)") — that specific claim is fixed,
           but the tool previously gave zero future recurrence protection for
           the same *shape* of claim. It still can't PROVE such a claim false
           (that requires reading and understanding prose, which this
           heuristic explicitly does not attempt) — it makes the claim
           visible for periodic manual review instead of invisible, which is
           the honest, bounded improvement available without turning this
           into an unbounded NLP-verification project. Known-legitimate
           non-code gates (human/manual/editorial review, sign-off, approval)
           are excluded from this advisory to avoid drowning real signal in
           routine prose.

Usage:
    python scripts/ci/checks/check_contract_claims.py [--paths glob ...]
    python scripts/ci/checks/check_contract_claims.py --json
Exit: 0 no findings, 1 findings present (non-fatal by default — see pre-commit
wiring notes; this is advisory, not a blocking gate, given its heuristic
nature and the cost of a false positive blocking an unrelated commit).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

_DEFAULT_GLOBS = [
    "skills/*.md",
    ".claude/commands/*.md",
    ".agents/skills/*/SKILL.md",
    ".kilocode/skills/*/SKILL.md",
    "scripts/pipeline/config/registry.yaml",
]

# Captures: subject token, verb, object token (a .py filename or bare identifier)
_CLAIM_RE = re.compile(
    r"(?P<subject>[A-Za-z_][A-Za-z0-9_.\-]*\.py|\bS-\d+\b)"
    r"\s+(?:MUST\s+be\s+|is\s+)?"
    r"(?P<verb>calls|invokes|uses|is gated on)\s+"
    r"(?P<object>[A-Za-z_][A-Za-z0-9_./\\-]*\.py|[A-Za-z_][A-Za-z0-9_]*\(\))",
    re.IGNORECASE,
)

# finding-2: a looser "is gated on <prose>" pattern with no .py/() requirement
# on the object — catches the exact shape of the original refresh-product.md
# bug, which _CLAIM_RE structurally cannot match (its object group requires a
# file/call-shaped token). Matches are advisory-only (see _KNOWN_HUMAN_GATES).
_GATED_ON_PROSE_RE = re.compile(
    r"(?P<subject>[A-Za-z_][A-Za-z0-9_.\-]*\.py|\bS-\d+\b)"
    r"\s+is\s+gated\s+on\s+(?P<object>[^.\n]+)",
    re.IGNORECASE,
)

# Non-code gates that are legitimately not machine-checkable — excluded from
# the advisory so it signals real drift, not routine editorial process.
_KNOWN_HUMAN_GATES = re.compile(
    r"\bhuman\b|\bmanual(?:ly)?\b|\beditorial\b|\breview(?:er)?\b|\bsign-?off\b|\bapproval\b",
    re.IGNORECASE,
)


def _module_stem(token: str) -> str:
    """'commands/foo/bar.py' or 'bar.py' or 'bar()' -> 'bar'."""
    token = token.rstrip("()")
    return Path(token.replace("\\", "/")).stem


def _find_source_file(stem: str) -> Path | None:
    """Best-effort: locate a single scripts/pipeline .py file matching stem."""
    candidates = list((_REPO_ROOT / "scripts" / "pipeline").rglob(f"{stem}.py"))
    if len(candidates) == 1:
        return candidates[0]
    # Prefer commands/ over lib/ over tests/ when ambiguous, else give up.
    non_test = [c for c in candidates if "tests" not in c.parts]
    if len(non_test) == 1:
        return non_test[0]
    return None


def _claim_verified(subject_stem: str, object_stem: str) -> bool:
    """True if subject's source imports OR subprocess-invokes object."""
    subject_path = _find_source_file(subject_stem)
    if subject_path is None:
        return True  # can't locate subject source -> nothing to contradict, don't flag
    try:
        text = subject_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True

    import_patterns = [
        rf"^\s*import\s+{re.escape(object_stem)}\b",
        rf"^\s*from\s+{re.escape(object_stem)}\s+import\b",
        rf"^\s*from\s+(?:lib|commands(?:\.[A-Za-z_]+)?)\.{re.escape(object_stem)}\s+import\b",
        rf"^\s*from\s+\.{re.escape(object_stem)}\s+import\b",
    ]
    for pat in import_patterns:
        if re.search(pat, text, re.MULTILINE):
            return True
    # subprocess invocation: the object's filename literal appears as a call target
    if re.search(rf"{re.escape(object_stem)}\.py", text):
        return True
    return False


def scan_file(path: Path) -> list[dict]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        try:
            display_path = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        except ValueError:
            display_path = str(path)  # outside the repo (e.g. a test fixture)

        matched_gated_on = False
        for m in _CLAIM_RE.finditer(line):
            subject_raw, verb, object_raw = m.group("subject"), m.group("verb"), m.group("object")
            if verb.lower() == "is gated on":
                matched_gated_on = True  # covered here (checkable) — don't also advisory-flag below
            if not subject_raw.endswith(".py") or not object_raw.endswith(".py"):
                continue  # only file-to-file claims are checkable; skip S-xx/bare-ident claims
            subject_stem = _module_stem(subject_raw)
            object_stem = _module_stem(object_raw)
            if subject_stem == object_stem:
                continue
            if not _claim_verified(subject_stem, object_stem):
                findings.append({
                    "file": display_path,
                    "line": lineno,
                    "claim": line.strip(),
                    "subject": subject_raw,
                    "verb": verb,
                    "object": object_raw,
                    "kind": "FALSE_CLAIM",
                })

        if matched_gated_on:
            continue  # this line's "is gated on" claim already handled above

        # finding-2: prose "is gated on" claims _CLAIM_RE structurally can't
        # match (object has no .py/() shape) — advisory, not a hard finding.
        for m in _GATED_ON_PROSE_RE.finditer(line):
            subject_raw = m.group("subject")
            object_raw = m.group("object").strip()
            if ".py" in object_raw:
                continue  # file-shaped object that just missed _CLAIM_RE's stricter token match
            if _KNOWN_HUMAN_GATES.search(object_raw):
                continue  # legitimate non-code gate, not a claim about pipeline enforcement
            findings.append({
                "file": display_path,
                "line": lineno,
                "claim": line.strip(),
                "subject": subject_raw,
                "verb": "is gated on",
                "object": object_raw,
                "kind": "UNVERIFIABLE_PROSE_CLAIM",
            })
    return findings


def scan(globs: list[str]) -> list[dict]:
    findings: list[dict] = []
    seen: set[Path] = set()
    for pattern in globs:
        # Accept an absolute/explicit path (a single file, e.g. from --paths
        # in a test) alongside repo-relative glob patterns.
        p = Path(pattern)
        if p.is_absolute() or p.is_file():
            matches: list[Path] = [p] if p.is_file() else []
        else:
            matches = sorted(_REPO_ROOT.glob(pattern))
        for path in matches:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            findings.extend(scan_file(path))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--paths", nargs="*", default=None,
                        help="Glob patterns to scan (default: skills/, .claude/commands/, registry.yaml)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    findings = scan(args.paths or _DEFAULT_GLOBS)
    hard = [f for f in findings if f.get("kind", "FALSE_CLAIM") == "FALSE_CLAIM"]
    advisory = [f for f in findings if f.get("kind") == "UNVERIFIABLE_PROSE_CLAIM"]

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        if hard:
            print(f"CONTRACT_CLAIM_DRIFT: {len(hard)} unverified claim(s):", file=sys.stderr)
            for f in hard:
                print(f"  {f['file']}:{f['line']}: {f['subject']} {f['verb']} {f['object']}",
                      file=sys.stderr)
                print(f"    \"{f['claim']}\"", file=sys.stderr)
        if advisory:
            print(f"ADVISORY: {len(advisory)} prose gating claim(s) not machine-verifiable "
                  "— periodic manual review recommended (never blocks):")
            for f in advisory:
                print(f"  {f['file']}:{f['line']}: \"{f['claim']}\"")
        if not hard and not advisory:
            print("check_contract_claims: no unverified claims found.")

    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
