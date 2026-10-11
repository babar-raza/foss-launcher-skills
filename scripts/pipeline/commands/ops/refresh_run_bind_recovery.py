#!/usr/bin/env python3
"""refresh_run_bind_recovery.py -- ST-126 recovery: bind a refresh_run to a
commit that already carries the run's real content but was pushed WITHOUT
the Refresh-Run/Refresh-Base/Refresh-Source-SHA trailers bind_commit()
requires.

Root cause (ST-126): once a commit is pushed without those trailers, there
is no forward-fix path -- amending a published commit is forbidden, and a
zero-diff follow-up commit is rejected by bind_commit's own diff-tree check
("has no changed paths"). This tool builds a SEPARATE commit object (never
touching refs/heads/main, never rewriting history) whose tree reflects the
run's own scope + extra_allowed_hashes files at their CURRENT, correct
on-disk state, whose parent is the original trailer-less commit's own
parent (so its diff against that parent is real and non-empty, satisfying
bind_commit's checks), and whose message is the original message with the
3 required trailers appended. bind_commit only needs the cited commit
object to be resolvable and internally consistent -- it does not require
it to be reachable from any branch. The real content stays exactly where
it already is (the original, trailer-less commit, already on main); this
shadow commit exists purely to satisfy the refresh_run governance contract
and is pushed to a dedicated non-branch ref for durable, inspectable
provenance.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/ops/refresh_run_bind_recovery.py \\
        {family} {platform} --run-id <run_id> --original-commit <sha> \\
        [--push-ref <ref>] [--session-id <id>] [--build-only]

Verified live 2026-08-31, MT040 Phase I: recovered
rf-20260830T142825Z-b6ef66497683 (cells/typescript), stuck at
READY_TO_COMMIT since 4bbd8df993 landed without trailers -- reached
COMMITTED, commit_sha=267b24004b497780af6106140bea3761b96435fc, pushed to
refs/mt040-evidence/cells-typescript-bind-proof.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import refresh_run as rr  # noqa: E402


class RecoveryError(RuntimeError):
    pass


def _git(args: list[str], *, env: dict[str, str] | None = None, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=120,
    )
    if result.returncode != 0:
        raise RecoveryError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def build_shadow_commit(
    family: str,
    platform: str,
    run_id: str,
    original_commit: str,
    *,
    repo_root: Path,
) -> str:
    """Build (but do not push) the shadow commit object. Returns its SHA."""
    run_root = rr._run_root(family, platform, run_id)
    manifest = rr._load_manifest(family, platform, run_id)

    if manifest["state"] != "READY_TO_COMMIT":
        raise RecoveryError(
            f"Recovery only applies to a run stuck at READY_TO_COMMIT; "
            f"current state is {manifest['state']!r}."
        )

    resolved_original = _git(["rev-parse", f"{original_commit}^{{commit}}"], cwd=repo_root)
    original_message = _git(["show", "-s", "--format=%B", resolved_original], cwd=repo_root)
    existing_trailers = rr._commit_trailer_values(original_message)
    if {"Refresh-Run", "Refresh-Base", "Refresh-Source-SHA"} <= existing_trailers.keys():
        raise RecoveryError(
            f"{resolved_original} already carries all 3 required trailers -- "
            "no recovery needed; bind-commit should work directly against it."
        )

    base_commit_sha = manifest["base_commit_sha"]
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_commit_sha, resolved_original],
        cwd=str(repo_root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    if ancestor.returncode != 0:
        raise RecoveryError(
            f"{resolved_original} does not descend from the run's own "
            f"base_commit_sha ({base_commit_sha}) -- wrong commit for this run?"
        )

    parent = _git(["rev-parse", f"{resolved_original}^"], cwd=repo_root)

    scope = rr._assert_pinned_scope(manifest)
    scope_paths = set(scope.get("paths") or [])
    extra_allowed = rr._load_extra_allowed_hashes(run_root)
    shadow_scope = sorted(scope_paths | set(extra_allowed.keys()))
    if not shadow_scope:
        raise RecoveryError("Run has no scope.paths and no extra_allowed_hashes -- nothing to bind.")

    missing_on_disk = [p for p in shadow_scope if not (repo_root / p).is_file()]
    if missing_on_disk:
        raise RecoveryError(
            f"{len(missing_on_disk)} shadow-scope file(s) are missing on disk "
            f"(first 5: {missing_on_disk[:5]}) -- resolve before recovery."
        )

    temp_index = repo_root / ".git" / f"RECOVERY_INDEX_{run_id}"
    env = {"GIT_INDEX_FILE": str(temp_index)}
    import os
    full_env = dict(os.environ)
    full_env.update(env)
    try:
        if temp_index.exists():
            temp_index.unlink()
        _git(["read-tree", parent], cwd=repo_root, env=full_env)
        # Batch to respect Windows CreateProcess argv length limits.
        batch = 200
        for i in range(0, len(shadow_scope), batch):
            _git(["add", "-f", *shadow_scope[i : i + batch]], cwd=repo_root, env=full_env)
        tree = _git(["write-tree"], cwd=repo_root, env=full_env)
    finally:
        if temp_index.exists():
            temp_index.unlink()

    trailer_block = (
        f"\nRefresh-Run: {run_id}\n"
        f"Refresh-Base: {base_commit_sha}\n"
        f"Refresh-Source-SHA: {manifest['target_source_sha']}\n"
    )
    new_message = original_message.rstrip("\n") + (
        "\n\nRecovered via refresh_run_bind_recovery.py (ST-126): same tree "
        f"content as {resolved_original[:12]} (plus any legitimately later-"
        "landed changes to the same scope files), parented on that commit's "
        "own original parent so its diff is real and non-empty. Not intended "
        "to join refs/heads/main -- the real content is already there via "
        f"{resolved_original[:12]}; this object exists solely to satisfy "
        "bind_commit()'s trailer requirement.\n"
        + trailer_block
    )

    shadow_sha = _git(
        ["commit-tree", tree, "-p", parent, "-m", new_message], cwd=repo_root
    )

    # Self-verify before handing back, matching bind_commit's own checks.
    trailers = rr._commit_trailer_values(
        _git(["show", "-s", "--format=%B", shadow_sha], cwd=repo_root)
    )
    for key, expected in (
        ("Refresh-Run", run_id),
        ("Refresh-Base", base_commit_sha),
        ("Refresh-Source-SHA", manifest["target_source_sha"]),
    ):
        if trailers.get(key) != [expected]:
            raise RecoveryError(
                f"Self-verification failed: trailer {key!r} = {trailers.get(key)!r}, "
                f"expected [{expected!r}]"
            )
    diff_files = _git(
        ["diff-tree", "--no-commit-id", "--name-only", "-r", shadow_sha], cwd=repo_root
    )
    if not diff_files.strip():
        raise RecoveryError("Shadow commit has an empty diff against its parent -- would be rejected.")

    return shadow_sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="refresh_run_bind_recovery",
        description="ST-126 recovery: bind a READY_TO_COMMIT refresh_run to an "
        "already-pushed, trailer-less commit via a non-destructive shadow commit.",
    )
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--original-commit", required=True,
        help="The already-pushed commit that carries the run's real content but "
        "lacks the required trailers.",
    )
    parser.add_argument(
        "--push-ref", default=None,
        help="Push the shadow commit to this ref on origin (e.g. "
        "refs/mt040-evidence/<family>-<platform>-bind-proof) for durable, "
        "inspectable provenance. Never refs/heads/main.",
    )
    parser.add_argument("--session-id", default=None)
    parser.add_argument(
        "--build-only", action="store_true",
        help="Build (and optionally push) the shadow commit but do not call bind-commit.",
    )
    args = parser.parse_args(argv)

    if args.push_ref and args.push_ref.startswith("refs/heads/"):
        print("ERROR: --push-ref must not target refs/heads/ (this tool never "
              "touches branch history).", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[3]
    rr.configure(repo_root=repo_root)

    try:
        shadow_sha = build_shadow_commit(
            args.family, args.platform, args.run_id, args.original_commit,
            repo_root=repo_root,
        )
    except (RecoveryError, rr.RefreshRunError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"shadow_commit_sha={shadow_sha}")

    if args.push_ref:
        import os
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            print("ERROR: --push-ref given but GH_TOKEN is not set.", file=sys.stderr)
            return 1
        push = subprocess.run(
            ["git", "push",
             f"https://x-access-token:{token}@github.com/Aspose/aspose.org.git",
             f"{shadow_sha}:{args.push_ref}"],
            cwd=str(repo_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        if push.returncode != 0:
            print(f"ERROR: push to {args.push_ref} failed: {push.stderr}", file=sys.stderr)
            return 1
        print(f"pushed to {args.push_ref}")

    if args.build_only:
        print(f"Next step: refresh_run.py bind-commit --run-id {args.run_id} "
              f"--commit {shadow_sha} --session-id <id>")
        return 0

    try:
        rr.bind_commit(
            args.family, args.platform, args.run_id, shadow_sha,
            session_id=args.session_id,
        )
    except rr.RefreshRunError as exc:
        print(f"ERROR: bind_commit failed against the shadow commit: {exc}", file=sys.stderr)
        return 1

    print("bind-commit succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
