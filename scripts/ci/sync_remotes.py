#!/usr/bin/env python3
"""sync_remotes.py -- fast-forward-only mirror of `main` between GitHub and GitLab.

Run on the platform named by --platform; it fetches the *other* platform's
`main`, and if the two tips differ, attempts a plain fast-forward push into
the other platform. The push itself (never `--force`) is the only
correctness gate: a prior SHA comparison is used solely as a cheap no-op
short-circuit, because a pre-push check-then-push sequence has no atomicity
guarantee across two independently-triggered CI jobs. A non-fast-forward
push means a genuine divergence -- this script never resolves one; on
--platform github it opens/updates a tracking issue via `gh` and always
exits non-zero so a human reconciles it.

Credential naming rule (GHGL-1): the GitLab-authenticating token is read
from the environment variable `gitlab_token` (lowercase) everywhere this is
technically possible. GitHub Actions itself forces secret names to
uppercase on storage (a platform constraint, not a choice made here) -- the
workflow that invokes this script maps that secret back onto an env var
literally named `gitlab_token` before calling in, so this script's own
contract never has to know about that exception. The GitHub-authenticating
token is read from `github_token` (lowercase; GitLab does not force casing).
"""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys

GITHUB_URL = "https://github.com/babar-raza/foss-launcher-skills.git"
GITLAB_URL = "https://gitlab.recruitize.ai/sialkot/cantt-smallize/foss-launcher-skills.git"

TARGET_URL = {"github": GITHUB_URL, "gitlab": GITLAB_URL}
CREDENTIAL_VAR = {"github": "github_token", "gitlab": "gitlab_token"}

# Alternate spellings seen historically in this project's own history/memory
# (gitlab_pat, GITLAB_PASSWORD, etc. -- all confirmed non-working). Detecting
# these when the *correct* name is absent turns a silent auth failure into a
# specific, actionable error instead of a generic 401.
WRONG_NAME_CANDIDATES = {
    "gitlab": ["GITLAB_TOKEN", "gitlab_pat", "GITLAB_PAT", "GITLAB_PASSWORD"],
    "github": ["GITHUB_TOKEN", "github_pat", "GH_TOKEN"],
}

EXIT_SYNCED = 0
EXIT_DIVERGENCE = 1
EXIT_INFRA_ERROR = 2

ISSUE_TITLE = "[sync-conflict] main branch diverged"


class SyncError(Exception):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def other_platform(platform: str) -> str:
    return "gitlab" if platform == "github" else "github"


def auth_header(target_platform: str, token: str) -> str:
    """Build a Basic-auth `http.extraheader` value -- never an embedded URL token."""
    if target_platform == "gitlab":
        basic = base64.b64encode(f"oauth2:{token}".encode()).decode()
    else:
        basic = base64.b64encode(f"{token}:x-oauth-basic".encode()).decode()
    return f"AUTHORIZATION: basic {basic}"


def resolve_credential(target_platform: str, env: dict) -> str:
    var = CREDENTIAL_VAR[target_platform]
    token = env.get(var)
    if token:
        return token

    seen_wrong = [name for name in WRONG_NAME_CANDIDATES[target_platform] if env.get(name)]
    lines = [f"Missing credential: environment variable '{var}' is not set."]
    if seen_wrong:
        lines.append(
            "Found alternately-named variable(s) instead: "
            + ", ".join(seen_wrong)
            + f". Per the GHGL-1 naming rule, only '{var}' is used -- rename it."
        )
    else:
        lines.append(f"Set '{var}' (lowercase) to a token scoped for pushing to {target_platform}.")
    raise SyncError("\n".join(lines), EXIT_INFRA_ERROR)


def run_git(args: list[str], extraheader: str | None = None) -> subprocess.CompletedProcess:
    cmd = ["git"]
    if extraheader is not None:
        cmd += ["-c", f"http.extraheader={extraheader}"]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True)


def rev_parse(ref: str) -> str:
    result = run_git(["rev-parse", ref])
    if result.returncode != 0:
        raise SyncError(f"git rev-parse {ref} failed: {result.stderr.strip()}", EXIT_INFRA_ERROR)
    return result.stdout.strip()


def fetch_target_head(target_url: str, branch: str, extraheader: str) -> str:
    result = run_git(["fetch", target_url, branch], extraheader=extraheader)
    if result.returncode != 0:
        raise SyncError(
            f"git fetch {target_url} {branch} failed: {result.stderr.strip()}", EXIT_INFRA_ERROR
        )
    return rev_parse("FETCH_HEAD")


def is_non_fast_forward(stderr: str) -> bool:
    lowered = stderr.lower()
    return "non-fast-forward" in lowered or "rejected" in lowered or "fetch first" in lowered


def would_be_fast_forward(target_sha: str, source_sha: str) -> bool:
    """True iff target_sha is an ancestor of source_sha -- i.e. pushing source
    onto target is a clean fast-forward, not a divergence. Used only to make
    --dry-run's report honest; the live path never trusts this and always
    lets the real push's own exit code decide (see module docstring)."""
    result = run_git(["merge-base", "--is-ancestor", target_sha, source_sha])
    return result.returncode == 0


def file_divergence_issue(source_sha: str, target_sha: str, target_platform: str, run_url: str) -> None:
    """Open or update a stable, findable GitHub issue. Only called for --platform github,
    so the GitLab-side job's token never needs GitLab-issue scope."""
    body = (
        f"Automated sync detected a non-fast-forward divergence.\n\n"
        f"- github main: {source_sha}\n"
        f"- gitlab main: {target_sha}\n"
        f"- run: {run_url}\n\n"
        f"No auto-merge or force-push was attempted. Reconcile manually, then the next "
        f"sync run will proceed normally once one side is a fast-forward of the other."
    )
    list_result = subprocess.run(
        ["gh", "issue", "list", "--search", ISSUE_TITLE, "--state", "open",
         "--label", "sync-conflict", "--json", "number"],
        capture_output=True, text=True,
    )
    number = None
    if list_result.returncode == 0 and list_result.stdout.strip():
        import json

        try:
            found = json.loads(list_result.stdout)
            if found:
                number = found[0]["number"]
        except (json.JSONDecodeError, KeyError, IndexError):
            number = None

    if number is not None:
        subprocess.run(["gh", "issue", "edit", str(number), "--body", body], capture_output=True, text=True)
    else:
        subprocess.run(
            ["gh", "issue", "create", "--title", ISSUE_TITLE, "--body", body, "--label", "sync-conflict"],
            capture_output=True, text=True,
        )


def sync(platform: str, branch: str, dry_run: bool, env: dict | None = None) -> int:
    env = os.environ if env is None else env
    target_platform = other_platform(platform)
    target_url = TARGET_URL[target_platform]

    try:
        token = resolve_credential(target_platform, env)
        header = auth_header(target_platform, token)
        source_sha = rev_parse("HEAD")
        target_sha = fetch_target_head(target_url, branch, header)
    except SyncError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    if source_sha == target_sha:
        print(f"Already in sync: {target_platform} {branch} is at {source_sha}.")
        return EXIT_SYNCED

    if dry_run:
        count_result = run_git(["rev-list", "--count", f"{target_sha}..{source_sha}"])
        ahead = count_result.stdout.strip() if count_result.returncode == 0 else "unknown"
        if would_be_fast_forward(target_sha, source_sha):
            print(
                f"DRY RUN: would push to {target_platform} {branch} "
                f"({target_sha[:12]} -> {source_sha[:12]}, {ahead} commit(s) ahead, "
                f"clean fast-forward). No push performed."
            )
            return EXIT_SYNCED
        print(
            f"DRY RUN: WOULD BE REJECTED -- {target_platform} {branch} has diverged "
            f"({target_sha[:12]} is not an ancestor of {source_sha[:12]}). A real push "
            f"would fail as non-fast-forward; this is a genuine divergence, not a clean "
            f"catch-up. No push performed.",
            file=sys.stderr,
        )
        return EXIT_DIVERGENCE

    push_result = run_git(["push", target_url, f"HEAD:{branch}"], extraheader=header)
    if push_result.returncode == 0:
        print(f"Synced {target_platform} {branch}: {target_sha[:12]} -> {source_sha[:12]}.")
        return EXIT_SYNCED

    if is_non_fast_forward(push_result.stderr):
        print(
            f"DIVERGENCE: {target_platform} {branch} could not be fast-forwarded "
            f"({target_sha[:12]} -> {source_sha[:12]} rejected). No force-push, no auto-merge.",
            file=sys.stderr,
        )
        if platform == "github":
            run_url = env.get("GITHUB_RUN_URL", "")
            try:
                file_divergence_issue(source_sha, target_sha, target_platform, run_url)
            except Exception as exc:  # pragma: no cover - best-effort, never masks the real failure
                print(f"(could not file/update tracking issue: {exc})", file=sys.stderr)
        return EXIT_DIVERGENCE

    print(f"INFRA ERROR pushing to {target_platform}: {push_result.stderr.strip()}", file=sys.stderr)
    return EXIT_INFRA_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=["github", "gitlab"],
                         help="Which platform this run's checkout belongs to (the source).")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return sync(args.platform, args.branch, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
