"""st054_campaign_worker.py — ST-054 TC-19
(plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).

Stateless executor over the ST-054-REMEDIATION taskcard ledger (seeded by
st054_seed_taskcards.py, driven via taskcard_cli.py -- never a duplicated
reimplementation of its claim/advance/ready logic, which is exactly the
mistake this design deliberately avoids per the governing plan's own
Reassessment: three-plus independently hand-copied run-state-machines
already exist in this repo sharing zero code; a fourth would repeat that
weakness, not fix it).

Loop, per product: `taskcard_cli.py ready` -> pick this product's next
eligible task -> `claim` (CAS-guarded; a losing race gets CONTENDED, not a
crash) -> dispatch by `step` to the real operation -> `advance` to CLOSED
with real evidence_refs on success, or BLOCKED_LOCAL with the error recorded
on failure (never silently skipped). All resumability lives in the ledger --
interrupting and restarting this script mid-campaign is safe by
construction: a claimed-but-abandoned task's lease expires and
`recover-expired` reclaims it; nothing here is stateful.

Steps (see st054_seed_taskcards.py's own docstring for why only 4, not the
originally-planned 5 -- the block/inline migrators already cover every
locale directly, no separate S-75 patch-derivation layer needed):
    block_migrate  -> package_install_migrator.run_migration()   (all locales)
    inline_migrate -> package_install_inline_migrator.migrate_file() per file,
                       reusing package_install_migrator.discover_files() for
                       the locale-inclusive file list (bypassing that
                       module's own English-only discover_files_english_only())
    verify         -> install_literal_sweep's methodology, scoped to one product
    commit         -> git_plumb_commit.py (the mandatory isolated-index path,
                       per CLAUDE.md, given this campaign routinely runs
                       alongside other concurrent sessions)

`needs_manual_review: true` (set by the seed script for cells/net) makes the
worker stop after `verify` and refuse to auto-advance `commit` -- it leaves
the commit taskcard at TODO with a note, for a human/agent to review the
diff and run `--product family/platform --step commit --confirm-manual-review`
explicitly.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.st054_campaign_worker \
        --product note/python --run-id pilot-1
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.st054_campaign_worker \
        --product note/python --once --run-id pilot-1   # single supervised step
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.st054_campaign_worker \
        --product cells/net --run-id batch-1 --confirm-manual-review   # after review
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from commands.content import package_install_migrator as block_migrator  # noqa: E402
from commands.content import package_install_inline_migrator as inline_migrator  # noqa: E402
from audit.package_install_literal import verify_package_install_literals  # noqa: E402
from lib.package_registry_data import load_registry  # noqa: E402
from commands.ops.st054_seed_taskcards import DEFAULT_MISSION_ID, STEPS, task_id  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT

_TASKCARD_CLI = _PIPELINE_ROOT / "commands" / "governance" / "taskcard_cli.py"
_GIT_PLUMB_COMMIT = _PIPELINE_ROOT / "commands" / "ops" / "git_plumb_commit.py"
_CHECKOUT_SYNC = _PIPELINE_ROOT / "commands" / "ops" / "checkout_sync.py"

_PYTHON = sys.executable


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    block_migrator.configure(repo_root=_REPO_ROOT)
    inline_migrator.configure(repo_root=_REPO_ROOT)


class WorkerBlocked(Exception):
    """Raised (not silently swallowed) when a step fails in a way the caller
    must see -- the taskcard is still advanced to BLOCKED_LOCAL first."""


# ── taskcard_cli.py wrapper (subprocess, never a duplicated reimplementation) ──

def _run_taskcard_cli(mission: str, args: list[str]) -> dict[str, Any]:
    cmd = [_PYTHON, str(_TASKCARD_CLI), "--mission", mission, "--repo-root", str(_REPO_ROOT), *args]
    result = subprocess.run(
        cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    stdout = result.stdout.strip()
    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        parsed = {"_raw_stdout": stdout, "_raw_stderr": result.stderr}
    parsed["_returncode"] = result.returncode
    return parsed


def _ready_tasks(mission: str, session_id: str) -> list[dict[str, Any]]:
    result = _run_taskcard_cli(mission, ["ready", "--session-id", session_id, "--json"])
    return result.get("eligible", [])


def _claim(mission: str, tid: str, expected: str, run_id: str, session_id: str) -> "dict[str, Any] | None":
    result = _run_taskcard_cli(
        mission, ["claim", "--task", tid, "--expected", expected,
                  "--run-id", run_id, "--session-id", session_id],
    )
    if result.get("_returncode") != 0:
        return None  # CONTENDED, not found, or lock timeout -- caller moves on
    return result


def _advance(
    mission: str, tid: str, expected: str, to: str, session_id: str,
    *, evidence: "list[str] | None" = None, fields: "dict[str, Any] | None" = None,
) -> "dict[str, Any] | None":
    args = ["advance", "--task", tid, "--expected", expected, "--to", to, "--session-id", session_id]
    for e in (evidence or []):
        args += ["--evidence", e]
    for k, v in (fields or {}).items():
        args += ["--field", f"{k}={v}"]
    result = _run_taskcard_cli(mission, args)
    if result.get("_returncode") != 0:
        return None
    return result


def _latest(mission: str, tid: str) -> "dict[str, Any] | None":
    result = _run_taskcard_cli(mission, ["latest", "--task", tid, "--json"])
    if result.get("_returncode") != 0:
        return None
    return result


# ── step implementations ────────────────────────────────────────────────────

def _step_block_migrate(family: str, platform: str, *, dry_run: bool) -> dict[str, Any]:
    registry = load_registry(_REPO_ROOT / "data" / "package_registry.json")
    summary = block_migrator.run_migration(family, platform, dry_run=dry_run, registry=registry)
    modified = [
        r["path"] for r in summary["results"]
        if r["result"] == block_migrator.R_MIGRATED
    ]
    return {
        "ok": True, "modified_files": modified,
        "detail": (f"files_checked={summary['files_checked']} "
                   f"files_migrated={summary['files_migrated']} "
                   f"block_replacements={summary['block_replacements']} "
                   f"inline_mentions_found_not_touched={summary['inline_mentions_found']} "
                   f"skipped_protected={summary['skipped_protected']} "
                   f"no_registry_entry={summary['no_registry_entry']}"),
    }


def _step_inline_migrate(family: str, platform: str, *, dry_run: bool) -> dict[str, Any]:
    """Reuses block_migrator.discover_files() (locale-inclusive, confirmed via
    direct read of its own docstring) rather than
    inline_migrator.discover_files_english_only() -- see this module's and
    st054_seed_taskcards.py's docstrings for why."""
    registry = load_registry(_REPO_ROOT / "data" / "package_registry.json")
    files = block_migrator.discover_files(family, platform)
    modified: list[str] = []
    checked = 0
    migrated = 0
    skipped_protected = 0
    no_registry_entry = 0
    for fp in files:
        checked += 1
        res = inline_migrator.migrate_file(fp, family, platform, dry_run=dry_run, registry=registry)
        if res["result"] == inline_migrator.R_NO_REGISTRY_ENTRY:
            no_registry_entry += 1
            continue
        if res["result"] == inline_migrator.R_SKIPPED_PROTECTED:
            skipped_protected += 1
            continue
        if res["result"] in (inline_migrator.R_MIGRATED, inline_migrator.R_DRY_RUN) and res["inline_replacements"] > 0:
            migrated += 1
            modified.append(res["path"])
    return {
        "ok": True, "modified_files": modified,
        "detail": (f"files_checked={checked} files_migrated={migrated} "
                   f"skipped_protected={skipped_protected} no_registry_entry={no_registry_entry}"),
    }


def _step_verify(family: str, platform: str) -> dict[str, Any]:
    registry = load_registry(_REPO_ROOT / "data" / "package_registry.json")
    entry = registry.get(family, {}).get(platform)
    if entry is None:
        return {"ok": False, "detail": f"no registry entry for {family}/{platform}", "findings": None}
    from commands.ops import install_literal_sweep  # local import: avoid configure() cross-talk at module load
    install_literal_sweep.configure(repo_root=_REPO_ROOT)
    files = install_literal_sweep._files_for(family, platform)
    total = 0
    files_with_findings = 0
    samples = []
    for fp in files:
        findings = verify_package_install_literals(fp, family, platform, registry=registry)
        if findings:
            files_with_findings += 1
            total += len(findings)
            if len(samples) < 5:
                samples.append({"path": str(fp), "message": findings[0].message})
    return {
        "ok": True, "findings": total, "files_with_findings": files_with_findings,
        "files_checked": len(files), "samples": samples,
        "detail": f"files_checked={len(files)} files_with_findings={files_with_findings} findings={total}",
    }


def _step_commit(
    family: str, platform: str, modified_files: list[str], *, skills: list[str], plan: str,
) -> dict[str, Any]:
    if not modified_files:
        return {"ok": True, "detail": "nothing to commit (no files modified by prior steps)", "commit_sha": None}

    message = (
        f"content({family}/{platform}): migrate literal install commands to shortcode (ST-054)\n\n"
        f"Automated via st054_campaign_worker.py (ST-054-REMEDIATION taskcard ledger) -- "
        f"block-level and inline-level literal install-command mentions replaced with the "
        f"registry-driven package-install/package-install-inline shortcodes, across English "
        f"source and all locale copies in one pass "
        f"(package_install_migrator.py's discover_files() already covers every locale; no "
        f"separate S-75 propagation step needed -- see the governing plan for detail).\n\n"
        f"{len(modified_files)} file(s) modified."
    )

    files_from_path = None
    cmd = [_PYTHON, str(_GIT_PLUMB_COMMIT)]
    if len(modified_files) > 400:
        import tempfile
        fd, files_from_path = tempfile.mkstemp(prefix="st054_commit_files_", suffix=".txt", dir=str(_REPO_ROOT / "reports"))
        with open(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(modified_files) + "\n")
        cmd += ["--files-from", files_from_path]
    else:
        cmd += ["--files", *modified_files]

    cmd += [
        "--message", message,
        "--co-author", "Claude Sonnet 5 <noreply@anthropic.com>",
        "--skills", *skills,
        "--plan", plan,
    ]

    result = subprocess.run(
        cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    if files_from_path:
        try:
            Path(files_from_path).unlink()
        except OSError:
            pass

    commit_sha = None
    for line in (result.stdout or "").splitlines():
        if line.startswith("commit_sha="):
            commit_sha = line.split("=", 1)[1].strip()

    if result.returncode != 0 or not commit_sha:
        return {
            "ok": False, "commit_sha": None,
            "detail": f"git_plumb_commit.py exit={result.returncode}: "
                      f"{(result.stdout or '')[-2000:]} {(result.stderr or '')[-2000:]}",
        }

    # Best-effort post-commit index-residue cleanup, mirroring the manual
    # remedy required during TC-17/TC-18 when git_plumb_commit.py's own
    # automatic sync aborted on concurrent index.lock contention.
    try:
        subprocess.run(
            [_PYTHON, str(_CHECKOUT_SYNC), "sync", "--old", f"{commit_sha}^", "--new", "HEAD",
             "--paths", *modified_files],
            cwd=str(_REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except Exception:
        pass  # best-effort; a real failure here is caught by the next session's own checkout_sync report

    return {"ok": True, "commit_sha": commit_sha, "detail": f"committed and pushed {commit_sha}"}


_STEP_FUNCS = {
    "block_migrate": _step_block_migrate,
    "inline_migrate": _step_inline_migrate,
    "verify": _step_verify,
    # "commit" is dispatched specially in process_one_step -- it needs the
    # accumulated modified_files from the two migrate steps' evidence, not
    # just its own (family, platform).
}


def _collect_modified_files(mission: str, family: str, platform: str) -> list[str]:
    """Reads block_migrate + inline_migrate's own recorded evidence (their
    modified-file lists, stored as evidence_refs) rather than re-deriving
    them -- avoids re-running either migrator a second time just to learn
    what it touched."""
    files: list[str] = []
    for step in ("block_migrate", "inline_migrate"):
        row = _latest(mission, task_id(family, platform, step))
        if row:
            files.extend(row.get("evidence_refs") or [])
    # de-dupe, preserve order
    seen = set()
    out = []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def preview_next_step(
    family: str, platform: str, *, mission: str = DEFAULT_MISSION_ID, session_id: str,
) -> "dict[str, Any] | None":
    """Read-only: shows what the next ready step WOULD do, in dry-run mode,
    WITHOUT claiming or advancing the taskcard. Deliberately a separate
    function from process_one_step rather than a `dry_run` flag threaded
    through it -- an earlier version passed dry_run through to the step
    functions but still claimed+advanced the taskcard to CLOSED regardless,
    which would have recorded "0 modified" as if the step were genuinely
    done with nothing to do, even when a real (non-dry-run) run might find
    real matches it simply wasn't allowed to write. Caught during the TC-20
    pilot itself, before it touched real content, precisely because the
    pilot was run supervised. Returns None if nothing is ready to preview."""
    eligible = _ready_tasks(mission, session_id)
    my_prefix = task_id(family, platform, "")
    candidates = [c for c in eligible if c["task_id"].startswith(my_prefix)]
    if not candidates:
        return None
    candidate = candidates[0]
    tid = candidate["task_id"]
    step = tid[len(my_prefix):]

    if step in ("verify", "commit"):
        return {"task_id": tid, "step": step, "detail": f"{step} has no dry-run preview form (verify is already read-only; commit needs real modified-file evidence)"}

    outcome = _STEP_FUNCS[step](family, platform, dry_run=True)
    return {"task_id": tid, "step": step, "detail": outcome["detail"]}


def process_one_step(
    family: str, platform: str, *, mission: str = DEFAULT_MISSION_ID,
    run_id: str, session_id: str,
    confirm_manual_review: bool = False, skills: "list[str] | None" = None,
) -> "dict[str, Any] | None":
    """Claim and execute exactly one ready step for this product, for real
    (never dry-run -- see preview_next_step() for a non-mutating preview).
    Returns None if nothing is currently ready (done, blocked, or contended
    by another session) -- never raises for a normal "nothing to do right
    now" outcome, only for a genuine internal error."""
    skills = skills or ["S-118"]
    plan = "plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md"

    eligible = _ready_tasks(mission, session_id)
    my_prefix = task_id(family, platform, "")
    candidates = [c for c in eligible if c["task_id"].startswith(my_prefix)]
    if not candidates:
        return None

    candidate = candidates[0]
    tid = candidate["task_id"]
    step = tid[len(my_prefix):]
    row = _latest(mission, tid)
    if row is None:
        return None

    if step == "commit" and row.get("needs_manual_review") and not confirm_manual_review:
        return {
            "task_id": tid, "step": step, "outcome": "AWAITING_MANUAL_REVIEW",
            "detail": f"{family}/{platform} is flagged needs_manual_review -- rerun with "
                      f"--confirm-manual-review after reviewing the diff to proceed",
        }

    claimed = _claim(mission, tid, candidate["status"], run_id, session_id)
    if claimed is None:
        return {"task_id": tid, "step": step, "outcome": "CONTENDED", "detail": "lost the claim race"}

    try:
        if step == "commit":
            modified = _collect_modified_files(mission, family, platform)
            outcome = _step_commit(family, platform, modified, skills=skills, plan=plan)
        elif step == "verify":
            outcome = _step_verify(family, platform)
        else:
            outcome = _STEP_FUNCS[step](family, platform, dry_run=False)
    except Exception as exc:  # noqa: BLE001 - must still advance the taskcard to BLOCKED_LOCAL
        outcome = {"ok": False, "detail": f"unhandled exception: {exc!r}"}

    if outcome.get("ok"):
        evidence = outcome.get("modified_files") or []
        if step == "commit" and outcome.get("commit_sha"):
            evidence = [outcome["commit_sha"]]
        elif step == "verify":
            evidence = [f"findings={outcome.get('findings')}"] + [s["path"] for s in outcome.get("samples", [])[:3]]
        if not evidence:
            evidence = [outcome["detail"]]
        _advance(mission, tid, "IN_PROGRESS", "CLOSED", session_id, evidence=evidence, fields={"detail": outcome["detail"]})
        return {"task_id": tid, "step": step, "outcome": "CLOSED", "detail": outcome["detail"]}

    _advance(
        mission, tid, "IN_PROGRESS", "BLOCKED_LOCAL", session_id,
        evidence=[outcome.get("detail", "no detail")], fields={"failure_detail": outcome.get("detail", "")},
    )
    return {"task_id": tid, "step": step, "outcome": "BLOCKED_LOCAL", "detail": outcome.get("detail")}


def process_product(
    family: str, platform: str, *, mission: str = DEFAULT_MISSION_ID,
    run_id: str, session_id: str, once: bool = False,
    confirm_manual_review: bool = False,
    max_steps: int = 10,
) -> list[dict[str, Any]]:
    """Loops process_one_step until nothing is ready for this product, it's
    blocked, or max_steps is hit (safety valve -- there are only 4 real steps
    per product; anything beyond that means something is looping, not
    progressing)."""
    results = []
    for _ in range(max_steps):
        result = process_one_step(
            family, platform, mission=mission, run_id=run_id, session_id=session_id,
            confirm_manual_review=confirm_manual_review,
        )
        if result is None:
            break
        results.append(result)
        if once:
            break
        if result["outcome"] in ("BLOCKED_LOCAL", "AWAITING_MANUAL_REVIEW", "CONTENDED"):
            break
    return results


def main(argv: "list[str] | None" = None) -> int:
    import argparse
    from session_identity import resolve_sanitized as _resolve_session_identity

    parser = argparse.ArgumentParser(prog="st054_campaign_worker")
    parser.add_argument("--product", required=True, metavar="family/platform")
    parser.add_argument("--mission", default=DEFAULT_MISSION_ID)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--preview", action="store_true",
        help="Show what the next ready step would do (dry-run) WITHOUT claiming or "
             "advancing the taskcard -- never mutates state. Mutually exclusive with "
             "actually running a step.",
    )
    parser.add_argument("--confirm-manual-review", action="store_true")
    args = parser.parse_args(argv)

    if "/" not in args.product:
        parser.error("--product must be family/platform")
    family, platform = args.product.split("/", 1)
    session_id = args.session_id or _resolve_session_identity()

    if args.preview:
        preview = preview_next_step(family, platform, mission=args.mission, session_id=session_id)
        if preview is None:
            print(f"{family}/{platform}: nothing ready to preview")
            return 0
        print(f"{preview['task_id']} ({preview['step']}, PREVIEW ONLY, taskcard untouched): {preview['detail']}")
        return 0

    results = process_product(
        family, platform, mission=args.mission, run_id=args.run_id, session_id=session_id,
        once=args.once, confirm_manual_review=args.confirm_manual_review,
    )
    if not results:
        print(f"{family}/{platform}: nothing ready (done, or blocked upstream)")
        return 0
    for r in results:
        print(f"{r['task_id']}: {r['outcome']} -- {r['detail']}")
    any_blocked = any(r["outcome"] == "BLOCKED_LOCAL" for r in results)
    return 1 if any_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
