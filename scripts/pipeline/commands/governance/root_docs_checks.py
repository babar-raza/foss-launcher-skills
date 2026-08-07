"""CONTRACT: deterministic checks for the /root-docs-refresh skill (S-121; plan:
C:\\Users\\prora\\.claude\\plans\\moonlit-strolling-sunset.md).

Full checks module for the seven root-level operator/governance docs (OPERATOR_GUIDE.md,
RUNBOOK.md, CODEX.md, GRADE_CONTRACT.md, LAYMAN_SYSTEM_STATUS_REVIEW.md, TASK_BACKLOG.md,
TASK_BACKLOG_20260521.md), called from root_docs_refresh_run.py's plan/recheck subcommands
AND imported directly (not reimplemented) by scripts/ci/checks/check_root_docs_truth.py, so
the manual refresh tool and the automated commit-time gate can never disagree about what
"correct" means -- they call the same functions.

Two tiers throughout, mirroring readme_refresh_checks.py's own documented contract exactly:
  - HARD_GATE: a non-empty result blocks the state-machine transition (root_docs_refresh_run.py)
    and fails the commit (check_root_docs_truth.py). Used only where the check is genuinely
    unambiguous -- a referenced script path either exists on disk or doesn't; a frozen version
    number either matches its code constant or doesn't.
  - HEURISTIC: a non-empty result is a prompt for the mandatory human/agent judgment pass,
    never an automatic fail. Used wherever "is this actually a problem" is a judgment call a
    script can't fully automate (is this hardcoded number legitimately historical prose, or a
    volatile fact that should be eliminated; does this file look dead, or just quiet).

Every function is pure: it takes plain strings/paths and returns plain data (list[dict]),
with no I/O beyond reading the inputs it's explicitly given (no network, no hidden global
state). This is what makes it safe to run unconditionally on every commit (cheap, fast) and
also call interactively from a skill -- same function, two callers, one truth. Idempotency
(same input -> byte-identical output) is a load-bearing property, not an incidental one; see
test_root_docs_checks.py's idempotency tests.

Functions:
  check_dead_path_references(text, repo_root) [[HARD_GATE]] -- every concrete scripts/ or
    docs/ path invoked inside a fenced code block must resolve on disk. Deliberately
    conservative: only lines that look like a real python/bash invocation of a script or doc
    path, and only paths containing no `{`/`}` placeholder braces, are checked -- this avoids
    flagging illustrative `{family}/{platform}` examples, which are common and legitimate.
  check_skill_id_references(text, skills_registry_text) [[HARD_GATE]] -- every "name (S-N)"
    pairing in prose must match the real (name, id) pair in docs/registries/skills.md.
  check_grade_contract_sync(grade_contract_text, content_eval_init_text, grade_config_text)
    [[HARD_GATE]] -- GRADE_CONTRACT.md-specific. The document's stated frozen
    EVALUATOR_FREEZE_VERSION baseline must match the live code constant in
    content_eval/__init__.py, and every canonical category-ceiling code present in
    grade_config.yaml must have a corresponding row in the document's own ceiling table.
  check_volatile_count_hardcoding(text) [[HEURISTIC]] -- flags a bare integer adjacent to
    "products"/"skills"/"platforms" that isn't inside an "as of <date>" or live-source-pointer
    pattern -- a candidate for the GENERATE class (see plan's Design section) rather than
    hand-maintained prose.
  check_dead_snapshot_file(path, repo_root, git_log_fn=None) [[HEURISTIC]] -- flags a root
    .md file matching the dead-snapshot shape: a single old commit (or no commits -- untracked
    scratch), no activity in the lookback window, and a canonical successor file plausibly
    supersedes it. git_log_fn is injectable (configure() seam) so tests don't depend on real
    git history.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

HARD_GATE = "HARD_GATE"
HEURISTIC = "HEURISTIC"

# Lines that look like a real invocation of a concrete scripts/ or docs/ path inside a
# fenced code block. Deliberately requires a python/bash-style invocation prefix so prose
# mentions and markdown links (already covered by check_onboarding_integrity.py's C4-LINKS)
# aren't double-flagged here.
_INVOCATION_PATH_RE = re.compile(
    r"\b(?:python|bash|\.venv/Scripts/python|\.venv/bin/python)\b[^\n]*?"
    r"\b((?:scripts|docs)/[\w./-]+\.(?:py|sh|md))\b"
)

_FENCE_RE = re.compile(r"```")

# "name (S-NN)" pairing, anchored to headings where the name is the FIRST token right
# after the heading marker, e.g. "### content-check (S-32)". Deliberately NOT a loose
# mid-line search: "### 10c. Triage findings to backlog (S-95)" would false-positive on
# "backlog" (a real skill name, S-88) even though the heading is citing S-95
# (discovery-triage) for an unrelated last word in a longer sentence -- found live
# against RUNBOOK.md:370 while building this check. Anchoring to "name is the first
# token after #+" cleanly separates a real name-then-ID label from a sentence that
# happens to end near a parenthetical ID.
_SKILL_ID_PAIR_RE = re.compile(r"^#{1,6}\s+([a-z][a-z0-9-]{2,40})\s*\(S-(\d+)\)\s*$", re.MULTILINE)

# Registry row: "| skill-name | S-NN | purpose... |"
_REGISTRY_ROW_RE = re.compile(r"^\|\s*([a-z][a-z0-9-]*)\s*\|\s*S-(\d+)\s*\|", re.MULTILINE)

_FREEZE_BASELINE_RE = re.compile(r"EVALUATOR_FREEZE_VERSION\s*=\s*\"?(\d+)\"?")
_INIT_FREEZE_RE = re.compile(r'^EVALUATOR_FREEZE_VERSION\s*(?::\s*str\s*\|\s*None\s*)?=\s*"?(\d+)"?', re.MULTILINE)
_CATEGORY_ROW_RE = re.compile(r"^\|\s*([A-Z]{2,3})\s*\|", re.MULTILINE)
_GRADE_CONFIG_CATEGORY_RE = re.compile(r"^\s*([A-Z]{2,3})_?[A-Z]*\s*:", re.MULTILINE)

_VOLATILE_COUNT_RE = re.compile(
    r"\b(\d{1,4})\+?\s+(?:active\s+)?(products?|skills?|platforms?)\b",
    re.IGNORECASE,
)
_AS_OF_CONTEXT_RE = re.compile(r"as of\s+\d{4}-\d{2}-\d{2}", re.IGNORECASE)
_LIVE_SOURCE_CONTEXT_RE = re.compile(r"data/products\.json|docs/registries/skills\.md|see\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# check_dead_path_references -- HARD_GATE
# ---------------------------------------------------------------------------


def check_dead_path_references(text: str, repo_root: Path) -> list[dict]:
    """Return one finding per invoked scripts/ or docs/ path that doesn't exist on disk.

    Hard gate -- scans fenced code blocks only, and only lines that look like a concrete
    python/bash invocation of a script or doc path with no `{...}` placeholder braces.
    """
    findings: list[dict] = []
    in_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if _FENCE_RE.search(line):
            in_block = not in_block
            continue
        if not in_block:
            continue
        m = _INVOCATION_PATH_RE.search(line)
        if not m:
            continue
        rel_path = m.group(1)
        if "{" in rel_path or "}" in rel_path:
            continue  # illustrative placeholder path (e.g. scripts/pipeline/{family}/run.py)
        resolved = (repo_root / rel_path).resolve()
        if not resolved.exists():
            findings.append({
                "check": "check_dead_path_references",
                "tier": HARD_GATE,
                "line": lineno,
                "path": rel_path,
                "message": f"line {lineno}: referenced path does not exist: {rel_path}",
            })
    return findings


# ---------------------------------------------------------------------------
# check_skill_id_references -- HARD_GATE
# ---------------------------------------------------------------------------


def _parse_skill_registry(skills_registry_text: str) -> dict[str, str]:
    """Return {skill_name: 'NN'} parsed from docs/registries/skills.md's table rows."""
    return {name: sid for name, sid in _REGISTRY_ROW_RE.findall(skills_registry_text)}


def check_skill_id_references(text: str, skills_registry_text: str) -> list[dict]:
    """Return one finding per "name (S-N)" mention whose N doesn't match the registry.

    Hard gate -- a skill ID cited in prose either matches the real registered ID for that
    skill name, or it's simply wrong (as OPERATOR_GUIDE.md's "content-check (S-32)" was --
    the registry says S-23; S-32 is a different skill, content-audit).
    """
    registry = _parse_skill_registry(skills_registry_text)
    findings: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in _SKILL_ID_PAIR_RE.finditer(line):
            # ^/$ anchor to the single-line string passed to finditer; MULTILINE is a
            # no-op here but kept on the compiled pattern for reuse against full text.
            name, cited_id = m.group(1), m.group(2)
            real_id = registry.get(name)
            if real_id is None:
                continue  # not a registered skill name -- not this check's concern
            if real_id != cited_id:
                findings.append({
                    "check": "check_skill_id_references",
                    "tier": HARD_GATE,
                    "line": lineno,
                    "skill": name,
                    "cited_id": f"S-{cited_id}",
                    "real_id": f"S-{real_id}",
                    "message": (
                        f"line {lineno}: '{name}' cited as S-{cited_id}, "
                        f"registry says S-{real_id}"
                    ),
                })
    return findings


# ---------------------------------------------------------------------------
# check_grade_contract_sync -- HARD_GATE (GRADE_CONTRACT.md-specific)
# ---------------------------------------------------------------------------


def check_grade_contract_sync(
    grade_contract_text: str,
    content_eval_init_text: str,
    grade_config_text: str,
) -> list[dict]:
    """Return findings where GRADE_CONTRACT.md's stated frozen state disagrees with the
    live code it claims to govern.

    Hard gate -- a document labeled FROZEN that disagrees with the code enforcing it is not
    a judgment call, it's a defect (this is the exact EVALUATOR_FREEZE_VERSION 17-vs-18 /
    missing EG_GROUNDING row mismatch this check exists to catch).
    """
    findings: list[dict] = []

    doc_matches = _FREEZE_BASELINE_RE.findall(grade_contract_text)
    init_match = _INIT_FREEZE_RE.search(content_eval_init_text)
    if doc_matches and init_match:
        doc_freeze = doc_matches[-1]  # most recent stated baseline, e.g. changelog tail
        code_freeze = init_match.group(1)
        if doc_freeze != code_freeze:
            findings.append({
                "check": "check_grade_contract_sync",
                "tier": HARD_GATE,
                "field": "EVALUATOR_FREEZE_VERSION",
                "doc_value": doc_freeze,
                "code_value": code_freeze,
                "message": (
                    f"GRADE_CONTRACT.md states frozen baseline {doc_freeze}, "
                    f"content_eval/__init__.py has {code_freeze}"
                ),
            })

    config_categories = {m.group(1) for m in _GRADE_CONFIG_CATEGORY_RE.finditer(grade_config_text)}
    doc_categories = {m.group(1) for m in _CATEGORY_ROW_RE.finditer(grade_contract_text)}
    missing = sorted(config_categories - doc_categories)
    for code in missing:
        findings.append({
            "check": "check_grade_contract_sync",
            "tier": HARD_GATE,
            "field": "category_ceiling_table",
            "missing_category": code,
            "message": (
                f"grade_config.yaml defines category '{code}' with no matching row "
                f"in GRADE_CONTRACT.md's §3 Category Ceiling Structure table"
            ),
        })

    return findings


# ---------------------------------------------------------------------------
# check_volatile_count_hardcoding -- HEURISTIC
# ---------------------------------------------------------------------------


def check_volatile_count_hardcoding(text: str) -> list[dict]:
    """Return one finding per bare count of products/skills/platforms with no "as of <date>"
    or live-source pointer nearby.

    Heuristic, not hard gate -- deliberately so. A bare small number in prose ("the 5
    pipeline steps") is common and legitimate; hard-failing on every match here would train
    people to bypass the gate, the exact failure mode that left check_agent_governance_
    surface.py permanently advisory. Surfaced for judgment: is this a GENERATE-class fact
    that should point at its live source instead, or legitimate historical prose.
    """
    findings: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _VOLATILE_COUNT_RE.search(line)
        if not m:
            continue
        if _AS_OF_CONTEXT_RE.search(line) or _LIVE_SOURCE_CONTEXT_RE.search(line):
            continue
        findings.append({
            "check": "check_volatile_count_hardcoding",
            "tier": HEURISTIC,
            "line": lineno,
            "matched": m.group(0),
            "message": (
                f"line {lineno}: hardcoded count '{m.group(0)}' with no 'as of <date>' or "
                f"live-source pointer -- consider generating from source instead"
            ),
        })
    return findings


# ---------------------------------------------------------------------------
# check_dead_snapshot_file -- HEURISTIC
# ---------------------------------------------------------------------------


def _default_git_log_fn(path: Path, repo_root: Path) -> list[str]:
    """Return ISO commit dates (newest first) touching path, via real git log."""
    result = subprocess.run(
        ["git", "log", "--follow", "--format=%cI", "--", str(path)],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def check_dead_snapshot_file(
    path: Path,
    repo_root: Path,
    lookback_days: int = 60,
    git_log_fn=None,
    now: datetime | None = None,
) -> dict | None:
    """Return a finding if path looks like a dead, superseded snapshot file, else None.

    Heuristic -- "dead" here means: exactly one commit ever touched the file (a one-shot
    snapshot, never revised) and that commit is older than lookback_days. A file with only
    one commit that was made yesterday is not dead, just new; a file with many commits is
    actively maintained regardless of age. This intentionally does not try to detect *which*
    file supersedes it -- that's exactly the kind of judgment call the human/agent
    remediation step in root_docs_refresh_run.py's plan resolves, not this function.
    """
    log_fn = git_log_fn or _default_git_log_fn
    dates = log_fn(path, repo_root)
    if len(dates) != 1:
        return None  # untracked (0) or actively revised (2+) -- not this heuristic's target
    try:
        last_touch = datetime.fromisoformat(dates[0])
    except ValueError:
        return None
    reference_now = now or datetime.now(tz=timezone.utc)
    age_days = (reference_now - last_touch).days
    if age_days < lookback_days:
        return None
    return {
        "check": "check_dead_snapshot_file",
        "tier": HEURISTIC,
        "path": str(path),
        "commit_count": 1,
        "age_days": age_days,
        "message": (
            f"{path}: single commit, {age_days} days old -- candidate for archival to "
            f"docs/_archive/root-orphans/ if a canonical successor now covers it"
        ),
    }


# ---------------------------------------------------------------------------
# CLI (for root_docs_refresh_run.py to shell out to, and for standalone debugging)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Run root-docs deterministic checks against a single file.",
    )
    parser.add_argument("file", help="Path to the file to check (relative to repo root)")
    parser.add_argument("--repo-root", default=None, help="Override repo root (default: auto-detect)")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parent.parent.parent.parent.parent
    target = (repo_root / args.file).resolve()
    text = target.read_text(encoding="utf-8")

    findings = list(check_dead_path_references(text, repo_root))

    skills_registry_path = repo_root / "docs" / "registries" / "skills.md"
    if skills_registry_path.exists():
        findings += check_skill_id_references(text, skills_registry_path.read_text(encoding="utf-8"))

    if target.name == "GRADE_CONTRACT.md":
        init_path = repo_root / "scripts" / "pipeline" / "content_eval" / "__init__.py"
        config_path = repo_root / "scripts" / "pipeline" / "content_eval" / "grade_config.yaml"
        if init_path.exists() and config_path.exists():
            findings += check_grade_contract_sync(
                text,
                init_path.read_text(encoding="utf-8"),
                config_path.read_text(encoding="utf-8"),
            )

    findings += check_volatile_count_hardcoding(text)

    hard_gate = [f for f in findings if f["tier"] == HARD_GATE]
    heuristic = [f for f in findings if f["tier"] == HEURISTIC]

    print(json.dumps({"file": args.file, "hard_gate": hard_gate, "heuristic": heuristic}, indent=2))
    return 1 if hard_gate else 0


if __name__ == "__main__":
    raise SystemExit(main())
