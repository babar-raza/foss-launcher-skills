"""check_skill_mirror_parity.py — pre-commit gate for skill/mirror drift.

CONTRACT: scripts/ci/checks/check_skill_mirror_parity.py
  purpose: block a commit from landing skill-file changes that leave the
           canonical skills/*.md source out of parity with its 3 provider
           mirrors (.claude/commands/*.md, .agents/skills/*/SKILL.md,
           .kilocode/skills/*/SKILL.md) for any skill the commit itself
           touches.
  root cause this closes: sync_skills.py (--check/--report) only detects
           drift, it has zero write capability; the tool that fixes drift,
           sync_providers.py, was previously undocumented outside a single CI
           YAML comment and was not run consistently. CI (skill-governance.yml)
           already runs sync_skills.py --check on every push, but this repo's
           real production path is direct-push-to-main (no PRs, no branch
           protection available on this plan) — a failing post-push CI check
           has no gating power. This script moves enforcement to the one
           gate every commit actually passes through: pre-commit.
  scope: intentionally narrow. Only skills touched by the CURRENT commit are
         checked — pre-existing drift in an untouched skill never blocks an
         unrelated commit (see check_parity_for_slugs() in sync_skills.py).
         This is a deliberate design choice, not a limitation to silently
         work around: it keeps the blast radius of this gate equal to the
         blast radius of the commit being made.
  usage:
    python scripts/ci/checks/check_skill_mirror_parity.py --staged-files <path> [<path> ...]
    Exit 0: no touched skill has drift (or no skill files were staged).
    Exit 1: at least one touched skill is out of parity — prints the drift
            and the fix command.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_DIR = str(_REPO_ROOT / "scripts" / "pipeline")
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)
# Import sync_skills as a BARE module (not "commands.ops.sync_skills") so this
# script and any test that also does `import sync_skills` (matching the
# convention documented in scripts/pipeline/tests/conftest.py) share the exact
# same sys.modules entry -- otherwise monkeypatching CANONICAL_DIR/PROVIDERS
# in a test patches a different module object than the one this script calls,
# and the gate silently checks the real repo tree instead of the test fixture.
_OPS_DIR = str(_REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops")
if _OPS_DIR not in sys.path:
    sys.path.insert(0, _OPS_DIR)

from sync_skills import check_parity_for_slugs  # noqa: E402

_SLUG_PATTERNS = [
    re.compile(r"^skills/([^/]+)\.md$"),
    re.compile(r"^\.claude/commands/([^/]+)\.md$"),
    re.compile(r"^\.agents/skills/([^/]+)/SKILL\.md$"),
    re.compile(r"^\.kilocode/skills/([^/]+)/SKILL\.md$"),
]


def extract_touched_slugs(staged_paths: list[str]) -> set[str]:
    """Return the set of skill slugs touched by the given staged file paths."""
    slugs: set[str] = set()
    for raw_path in staged_paths:
        normalized = raw_path.replace("\\", "/")
        for pattern in _SLUG_PATTERNS:
            m = pattern.match(normalized)
            if m:
                slugs.add(m.group(1))
                break
    return slugs


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--staged-files", nargs="*", default=[],
                         help="Staged file paths (from git diff --cached --name-only)")
    args = parser.parse_args(argv)

    touched_slugs = extract_touched_slugs(args.staged_files)
    if not touched_slugs:
        print("[skill-mirror-parity] No skill/mirror files staged — skipping.")
        return 0

    issues = check_parity_for_slugs(touched_slugs)
    if not issues:
        print(f"[skill-mirror-parity] PASS — {len(touched_slugs)} touched skill(s) "
              f"in parity: {', '.join(sorted(touched_slugs))}")
        return 0

    print("[skill-mirror-parity] BLOCKED — the following touched skill(s) are "
          "out of parity between canonical and their provider mirrors:")
    seen_slugs = set()
    for issue in issues:
        seen_slugs.add(issue["slug"])
        print(f"  [{issue['type']}] {issue['provider']}/{issue['slug']}: {issue['detail']}")
    print("")
    print(f"Fix: PYTHONPATH=scripts/pipeline .venv/Scripts/python "
          f"scripts/pipeline/commands/ops/sync_providers.py")
    print("Then verify: PYTHONPATH=scripts/pipeline .venv/Scripts/python "
          "scripts/pipeline/commands/ops/sync_skills.py --check")
    print("")
    print("If a provider mirror (not canonical) holds the newer/correct content for one of "
          "these skills, port it into skills/{slug}.md FIRST — sync_providers.py is "
          "one-directional (canonical -> mirrors) and will silently overwrite a mirror-only "
          "improvement otherwise.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
