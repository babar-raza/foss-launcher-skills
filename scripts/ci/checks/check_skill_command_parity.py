#!/usr/bin/env python3
"""check_skill_command_parity.py — RPR-G-02: detect divergence across skill mirrors.

A skill is authored in THREE mirror locations that must stay in sync:
  - .agents/skills/{name}/SKILL.md      (canonical)
  - .claude/commands/{name}.md          (Claude command mirror)
  - .kilocode/skills/{name}/SKILL.md     (Kilocode mirror)

The 2026-06-27/07-02 body-refresh silent revert happened because only the
.claude/commands mirror was wired (never the canonical .agents version), then
only the mirror was reverted — the two were never in sync in either direction and
nothing reading the canonical file alone would notice (plan §2.2). This check
compares the mirrors' normalized content and flags any skill whose mirrors diverge.

Modes:
  (default)   Report every divergent skill; exit 0 (advisory / nightly drift scan).
  --strict    Exit 1 if any non-allowlisted skill's mirrors diverge (CI gate).
  --files ... Co-change mode: given changed files, fail (exit 1) if a mirror of a
              refresh-chain skill changed but its siblings did not match — unless the
              commit message carries a `SKILL-COMMAND-DIVERGENCE-ACK:` trailer.

An allowlist (KNOWN_DIVERGENT) records skills whose mirrors are intentionally or
historically divergent, so --strict can be enabled without first cleaning every
pre-existing drift. Entries should be removed as drift is reconciled.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_AGENTS_DIR = REPO_ROOT / ".agents" / "skills"
_CLAUDE_DIR = REPO_ROOT / ".claude" / "commands"
_KILO_DIR = REPO_ROOT / ".kilocode" / "skills"

# Skills whose mirrors are known to diverge today (pre-existing, not introduced by
# RPR-G-02). Remove entries as they are reconciled. Keeping this explicit is the
# honest alternative to silently passing on drift.
KNOWN_DIVERGENT: set[str] = set()

_ACK_TRAILER = re.compile(r"SKILL-COMMAND-DIVERGENCE-ACK:", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Line-ending- and trailing-whitespace-insensitive normalization."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in unified.split("\n")).strip()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def mirror_paths(name: str) -> dict[str, Path]:
    return {
        "agents": _AGENTS_DIR / name / "SKILL.md",
        "claude": _CLAUDE_DIR / f"{name}.md",
        "kilocode": _KILO_DIR / name / "SKILL.md",
    }


def find_skill_names() -> list[str]:
    """Every skill that has a canonical .agents/skills/{name}/SKILL.md."""
    if not _AGENTS_DIR.is_dir():
        return []
    names = []
    for d in sorted(_AGENTS_DIR.iterdir()):
        if d.is_dir() and (d / "SKILL.md").is_file():
            names.append(d.name)
    return names


def compare_skill(name: str) -> dict:
    """Return {name, present: [...], divergent: bool, divergent_mirrors: [...]}.

    Only mirrors that EXIST are compared (a skill may legitimately have no kilocode
    mirror). Divergence = two existing mirrors whose normalized content differs.
    """
    paths = mirror_paths(name)
    contents = {}
    for mirror, p in paths.items():
        raw = _read(p)
        if raw is not None:
            contents[mirror] = _normalize(raw)

    present = sorted(contents.keys())
    if len(present) < 2:
        return {"name": name, "present": present, "divergent": False, "divergent_mirrors": []}

    canonical = contents.get("agents") or contents[present[0]]
    divergent_mirrors = [m for m in present if contents[m] != canonical]
    return {
        "name": name,
        "present": present,
        "divergent": bool(divergent_mirrors),
        "divergent_mirrors": divergent_mirrors,
    }


def scan_all() -> list[dict]:
    return [compare_skill(n) for n in find_skill_names()]


def _skill_name_for_file(path: str) -> str | None:
    """Given a changed file path, return the skill name if it is a mirror file."""
    p = path.replace("\\", "/")
    m = re.search(r"\.agents/skills/([^/]+)/SKILL\.md$", p)
    if m:
        return m.group(1)
    m = re.search(r"\.claude/commands/([^/]+)\.md$", p)
    if m:
        return m.group(1)
    m = re.search(r"\.kilocode/skills/([^/]+)/SKILL\.md$", p)
    if m:
        return m.group(1)
    return None


def check_cochange(changed_files: list[str], commit_msg: str = "") -> list[str]:
    """Co-change mode: for each skill touched by changed_files, fail if its mirrors
    diverge, unless the commit message carries the ACK trailer. Returns problem strings."""
    if _ACK_TRAILER.search(commit_msg or ""):
        return []
    touched = {n for f in changed_files if (n := _skill_name_for_file(f))}
    problems = []
    for name in sorted(touched):
        if name in KNOWN_DIVERGENT:
            continue
        result = compare_skill(name)
        if result["divergent"]:
            problems.append(
                f"{name}: mirror(s) {result['divergent_mirrors']} diverge from canonical "
                f"after this change (add SKILL-COMMAND-DIVERGENCE-ACK: <reason> to override)"
            )
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Detect divergence across skill mirror files (RPR-G-02).")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any non-allowlisted skill diverges")
    parser.add_argument("--files", nargs="*", help="Co-change mode: changed files to check")
    parser.add_argument("--commit-msg", default="", help="Commit message (for the ACK trailer)")
    args = parser.parse_args(argv)

    if args.files is not None:
        problems = check_cochange(args.files, args.commit_msg)
        if problems:
            print(f"SKILL-COMMAND PARITY: {len(problems)} co-change violation(s):")
            for p in problems:
                print(f"  - {p}")
            return 1
        print("OK: no skill/command co-change parity violations.")
        return 0

    results = scan_all()
    divergent = [r for r in results if r["divergent"] and r["name"] not in KNOWN_DIVERGENT]
    for r in divergent:
        print(f"  DIVERGENT: {r['name']} — mirrors {r['divergent_mirrors']} differ from canonical")
    print(f"Scanned {len(results)} skills; {len(divergent)} divergent (excluding "
          f"{len(KNOWN_DIVERGENT)} allowlisted).")
    if args.strict and divergent:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
