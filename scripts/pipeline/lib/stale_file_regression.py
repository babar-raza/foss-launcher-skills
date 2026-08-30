"""stale_file_regression.py — OID-based stale-file revert detection core
(2026-08-29 stale-guard plan, T1 / TC-SG-04).

Replaces the text-comparison engine inside
scripts/ci/checks/check_stale_file_regression.py, which compared
locale-decoded `git show` output against UTF-8 file reads (inert for any
non-ASCII file in worktree mode; silently exit-0 on cp1252-unmappable bytes —
ST-096) and used "commits since MY session began" as the window (missed the
2026-08-07 `55586b637c` revert of 5-day-old commits — RC0).

Design points, each carrying a verified rationale:

- **Object IDs, never content.** Proposed state and historical states are
  compared as git blob OIDs. Worktree hashing goes through the clean filter
  (`git hash-object --stdin-paths`), so `core.autocrlf=true` worktrees (63.7 %
  of the relevant files here are `i/lf w/crlf`) hash to their blob OIDs. No
  file content ever crosses into Python, so no codec can make two equal blobs
  look different or two different blobs look equal.

- **Window = oldest(session base, bounded lookback), never "session only".**
  The finding predicate for path P: let L be the newest first-parent commit in
  `window..head` touching P; finding iff proposed(P) == oid(L^:P) and
  != oid(L:P). Monotonic: an older ancestor window only ever ADDS findings.
  Findings are classed `session` (L is inside the resolved session window —
  today's guarantee) vs `lookback` (only visible through the wider window —
  the RC0 class), so consumers can soft-launch the widened portion.

- **Membership, not ancestry-of-base.** "Intervening" means L ∈ window..head
  (a side-branch commit merged after the window boundary counts — the old
  `merge-base --is-ancestor base L` predicate missed those; adversarial A3).

- **One history pass.** `git log --first-parent --diff-merges=first-parent -z
  --name-only` over the window yields the newest touching commit per path in
  a single process — no per-file `git log` (877 paths in 0.22 s here).

- **NUL-delimited, bytes-parsed listings** (`core.quotepath` is true by
  default everywhere except this machine; octal-escaped paths would silently
  drop out of any text intersection — adversarial A1).

- **Deletions**: a proposed deletion is never a finding (deletions are
  DGR-governed); re-creating a file the intervening commit deleted, with the
  pre-deletion blob, IS a finding; a file created by L (no parent blob) is not.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]

_REPO_ROOT = _DEFAULT_REPO_ROOT
_COMMAND_RUNNER: Callable[..., "subprocess.CompletedProcess"] = subprocess.run
_LOOKBACK_DAYS = 14
_LOOKBACK_MAX_COMMITS = 5000
_CHUNK = 300

_TEXT_KW = dict(text=True, encoding="utf-8", errors="replace")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def configure(
    *,
    repo_root: "Path | str | None" = None,
    command_runner: "Callable[..., subprocess.CompletedProcess] | None" = None,
    lookback_days: "int | None" = None,
    lookback_max_commits: "int | None" = None,
) -> None:
    """Test seam. Called with no arguments, resets to defaults."""
    global _REPO_ROOT, _COMMAND_RUNNER, _LOOKBACK_DAYS, _LOOKBACK_MAX_COMMITS
    if repo_root is None and command_runner is None and lookback_days is None \
            and lookback_max_commits is None:
        _REPO_ROOT = _DEFAULT_REPO_ROOT
        _COMMAND_RUNNER = subprocess.run
        _LOOKBACK_DAYS = 14
        _LOOKBACK_MAX_COMMITS = 5000
        return
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
    if command_runner is not None:
        _COMMAND_RUNNER = command_runner
    if lookback_days is not None:
        _LOOKBACK_DAYS = lookback_days
    if lookback_max_commits is not None:
        _LOOKBACK_MAX_COMMITS = lookback_max_commits


class StaleCheckInfraError(RuntimeError):
    """The check could not run (git failure, missing capture). Never a verdict."""


@dataclass(frozen=True)
class Baseline:
    window_sha: "str | None"          # the effective (widest) window boundary
    source: str                       # "explicit" | "session" | "lookback" | "none"
    session_sha: "str | None" = None  # the session's own base when resolved
    session_id: "str | None" = None
    detail: str = ""


@dataclass(frozen=True)
class Finding:
    path: str
    intervening_commit: str
    proposed_oid: "str | None"
    parent_oid: "str | None"
    intervening_oid: "str | None"
    finding_class: str                 # "session" | "lookback"
    override_token_id: "str | None" = None

    def to_dict(self) -> dict:
        return {
            "file": self.path,
            "intervening_commit": self.intervening_commit,
            "proposed_oid": self.proposed_oid,
            "parent_oid": self.parent_oid,
            "intervening_oid": self.intervening_oid,
            "class": self.finding_class,
            "override_token_id": self.override_token_id,
        }


@dataclass
class Report:
    status: str                        # "clean" | "regression" | "no_baseline" | "error"
    baseline: Baseline
    mode: str                          # "index" | "worktree"
    head: str
    files_checked: int = 0
    window_paths: int = 0
    findings: "list[Finding]" = field(default_factory=list)
    diagnostics: "list[str]" = field(default_factory=list)

    def blocking(self, *, wide_findings: str = "warn") -> "list[Finding]":
        """Findings that must block: uncovered session-class always; uncovered
        lookback-class only when wide_findings == "block" (soft-launch seam)."""
        out = []
        for f in self.findings:
            if f.override_token_id is not None:
                continue
            if f.finding_class == "session" or wide_findings == "block":
                out.append(f)
        return out

    def to_dict(self) -> dict:
        return {
            "schema": 1,
            "status": self.status,
            "mode": self.mode,
            "head": self.head,
            "base_sha": self.baseline.window_sha,
            "source": self.baseline.source,
            "session_id": self.baseline.session_id,
            "session_sha": self.baseline.session_sha,
            "files_checked": self.files_checked,
            "window_paths": self.window_paths,
            "findings": [f.to_dict() for f in self.findings],
            "diagnostics": self.diagnostics,
        }


def _git(args: "list[str]", *, repo_root: Path,
         input_bytes: "bytes | None" = None, binary_out: bool = False,
         ) -> "subprocess.CompletedProcess":
    kwargs: dict = dict(cwd=str(repo_root), capture_output=True)
    if input_bytes is not None or binary_out:
        kwargs["text"] = False
        if input_bytes is not None:
            kwargs["input"] = input_bytes
    else:
        kwargs.update(_TEXT_KW)
    result = _COMMAND_RUNNER(["git", *args], **kwargs)
    if result.stdout is None or result.stderr is None:
        raise StaleCheckInfraError(
            f"git {' '.join(args)}: no captured output (reader failure)"
        )
    return result


def _rev_parse(rev: str, *, repo_root: Path) -> "str | None":
    result = _git(["rev-parse", "--verify", "-q", rev], repo_root=repo_root)
    sha = (result.stdout or "").strip()
    return sha if result.returncode == 0 and sha else None


def _is_ancestor(ancestor: str, descendant: str, *, repo_root: Path) -> bool:
    result = _git(["merge-base", "--is-ancestor", ancestor, descendant], repo_root=repo_root)
    return result.returncode == 0


def _lookback_boundary(head: str, *, repo_root: Path) -> "str | None":
    """Newest first-parent commit older than the lookback window, capped so the
    window never exceeds _LOOKBACK_MAX_COMMITS commits."""
    time_b = _git(["rev-list", "--first-parent", "-n1",
                   f"--before={_LOOKBACK_DAYS} days ago", head], repo_root=repo_root)
    time_sha = (time_b.stdout or "").strip() or None
    skip_b = _git(["rev-list", "--first-parent", f"--skip={_LOOKBACK_MAX_COMMITS}",
                   "-n1", head], repo_root=repo_root)
    skip_sha = (skip_b.stdout or "").strip() or None

    if time_sha and skip_sha:
        # Use the NEWER boundary (shallower window): the cap wins over time.
        return time_sha if _is_ancestor(skip_sha, time_sha, repo_root=repo_root) else skip_sha
    if time_sha:
        return time_sha
    if skip_sha:
        return skip_sha
    # Young repo: whole history is inside the window -> boundary = root commit.
    root_list = _git(["rev-list", "--first-parent", "--max-parents=0", head],
                     repo_root=repo_root)
    roots = (root_list.stdout or "").split()
    return roots[-1] if roots else None


def resolve_baseline(
    *,
    explicit_sha: "str | None",
    session_ctx=None,          # session_ledger.SessionContext | None (duck-typed)
    head: str,
    repo_root: "Path | None" = None,
) -> Baseline:
    """Effective window = oldest(explicit/session base, lookback boundary).

    An explicit sha that is not an ancestor of head is ignored with a
    diagnostic (adversarial A4/B1) rather than exploding the range. Identity
    is NOT required: with no resolvable session the window is the lookback
    boundary (`source="lookback"`) — the 2026-08-07 miss showed staleness
    does not respect session boundaries."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    detail_parts: "list[str]" = []

    session_sha = None
    session_id = None
    if session_ctx is not None and getattr(session_ctx, "status", None) == "resolved":
        session_id = getattr(session_ctx, "session_id", None)
        candidate = getattr(session_ctx, "base_sha", None)
        if candidate and _rev_parse(candidate, repo_root=root) \
                and _is_ancestor(candidate, head, repo_root=root):
            session_sha = candidate
        elif candidate:
            detail_parts.append(f"session base {candidate[:10]} is not an ancestor of head; ignored")

    anchor = None
    anchor_source = None
    if explicit_sha:
        if _SHA_RE.match(explicit_sha or "") or _rev_parse(explicit_sha, repo_root=root):
            resolved = _rev_parse(explicit_sha, repo_root=root)
            if resolved and _is_ancestor(resolved, head, repo_root=root):
                anchor, anchor_source = resolved, "explicit"
            else:
                detail_parts.append(f"explicit base {explicit_sha[:10]} is not an ancestor of head; ignored")
        else:
            detail_parts.append(f"explicit base {explicit_sha[:10]!r} does not resolve; ignored")
    if anchor is not None and anchor_source == "explicit":
        # An accepted explicit base IS the caller's known window: findings
        # after it are session-class (blocking), exactly today's guarantee --
        # the lookback below can only widen the WARN-class coverage beyond it.
        session_sha = anchor
    if anchor is None and session_sha:
        anchor, anchor_source = session_sha, "session"

    boundary = _lookback_boundary(head, repo_root=root)
    if boundary is None and anchor is None:
        return Baseline(window_sha=None, source="none", session_sha=session_sha,
                        session_id=session_id, detail="; ".join(detail_parts) or "no window computable")

    if anchor is None:
        window, source = boundary, "lookback"
    elif boundary is None:
        window, source = anchor, anchor_source
    elif _is_ancestor(anchor, boundary, repo_root=root) and anchor != boundary:
        window, source = anchor, anchor_source          # anchor is older -> widest wins
    else:
        window, source = boundary, "lookback"

    return Baseline(window_sha=window, source=source, session_sha=session_sha,
                    session_id=session_id, detail="; ".join(detail_parts))


def intervening_commits(
    window_sha: str, head: str, paths: "list[str]", *, repo_root: "Path | None" = None,
) -> "dict[str, str]":
    """path -> NEWEST first-parent commit in window..head touching it, for the
    given paths only. One history pass, NUL-delimited, bytes-parsed."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    wanted = {p.replace("\\", "/") for p in paths}
    result = _git(["log", "--first-parent", "--diff-merges=first-parent", "-z",
                   "--name-only", "--format=%x01%H", f"{window_sha}..{head}"],
                  repo_root=root, binary_out=True)
    if result.returncode != 0:
        raise StaleCheckInfraError(
            f"git log {window_sha[:10]}..{head[:10]} failed: "
            f"{(result.stderr or b'').decode('utf-8', 'replace')[:200]}"
        )
    out: "dict[str, str]" = {}
    current_sha: "str | None" = None
    for token in (result.stdout or b"").split(b"\0"):
        token = token.strip(b"\n")
        if not token:
            continue
        if token.startswith(b"\x01"):
            # \x01<sha> record marker (never a valid path byte here); a path
            # list for the PREVIOUS commit may share this token after a \n.
            parts = token.split(b"\n")
            current_sha = parts[0][1:].decode("ascii", "replace")
            extra_paths = parts[1:]
        else:
            extra_paths = token.split(b"\n")
        for raw in extra_paths:
            if not raw or raw.startswith(b"\x01"):
                if raw.startswith(b"\x01"):
                    current_sha = raw[1:].decode("ascii", "replace")
                continue
            path = raw.decode("utf-8", "surrogateescape")
            if path in wanted and path not in out and current_sha:
                out[path] = current_sha
    return out


def _batch_check_oids(specs: "list[str]", *, repo_root: Path) -> "dict[str, str | None]":
    """'rev:path' -> blob OID (None when missing or not a blob)."""
    out: "dict[str, str | None]" = {s: None for s in specs}
    if not specs:
        return out
    stdin_bytes = "\n".join(specs).encode("utf-8", "surrogateescape") + b"\n"
    result = _git(["cat-file", "--batch-check"], repo_root=repo_root, input_bytes=stdin_bytes)
    lines = (result.stdout or b"").decode("utf-8", "surrogateescape").splitlines()
    for spec, line in zip(specs, lines):
        parts = line.split()
        if len(parts) >= 2 and parts[-1] != "missing" and parts[1] == "blob":
            out[spec] = parts[0]
    return out


def proposed_oids(
    paths: "list[str]", *, mode: str, repo_root: "Path | None" = None,
    index_file: "str | None" = None, head: str = "HEAD",
) -> "dict[str, str | None]":
    """Proposed blob OID per path. mode="index": the (possibly GIT_INDEX_FILE-
    redirected) index entry, falling back to head's blob for unlisted paths;
    mode="worktree": clean-filtered hash of the on-disk bytes (None = absent =
    a proposed deletion, never a finding)."""
    import os
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    normalized = [p.replace("\\", "/") for p in paths]
    out: "dict[str, str | None]" = {p: None for p in normalized}

    if mode == "worktree":
        present = [p for p in normalized if (root / p).is_file()]
        if present:
            stdin_bytes = "\n".join(present).encode("utf-8", "surrogateescape") + b"\n"
            result = _COMMAND_RUNNER(
                ["git", "hash-object", "--stdin-paths"], cwd=str(root),
                capture_output=True, input=stdin_bytes, text=False,
            )
            if result.returncode != 0:
                raise StaleCheckInfraError(
                    "git hash-object --stdin-paths failed: "
                    + (result.stderr or b"").decode("utf-8", "replace")[:200]
                )
            for path, oid in zip(present, (result.stdout or b"").decode("ascii", "replace").split()):
                out[path] = oid
        return out

    env = {**os.environ}
    if index_file:
        env["GIT_INDEX_FILE"] = index_file
    for i in range(0, len(normalized), _CHUNK):
        chunk = normalized[i:i + _CHUNK]
        result = _COMMAND_RUNNER(
            ["git", "ls-files", "-s", "-z", "--", *chunk], cwd=str(root),
            capture_output=True, env=env, text=False,
        )
        if result.returncode != 0:
            raise StaleCheckInfraError(
                "git ls-files -s failed: "
                + (result.stderr or b"").decode("utf-8", "replace")[:200]
            )
        for entry in (result.stdout or b"").split(b"\0"):
            if not entry.strip():
                continue
            meta, _tab, path_b = entry.partition(b"\t")
            fields = meta.split()
            if len(fields) >= 3 and fields[2] == b"0":
                out[path_b.decode("utf-8", "surrogateescape")] = fields[1].decode("ascii")
    # Paths without an index entry: staged deletion (None). Nothing else to do.
    return out


def detect_regressions(
    paths: "list[str]",
    *,
    baseline: Baseline,
    head: str,
    mode: str,
    repo_root: "Path | None" = None,
    index_file: "str | None" = None,
    override_lookup: "Callable[[str], dict | None] | None" = None,
    content_prefix_session_only: bool = True,
) -> Report:
    """Evaluate the revert predicate for `paths`. content/ paths are, by the
    plan's D-A(ii) decision, evaluated only in the session window until the
    content-scale replay is measured (content_prefix_session_only)."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    normalized = [p.replace("\\", "/") for p in paths]

    if baseline.window_sha is None:
        return Report(status="no_baseline", baseline=baseline, mode=mode, head=head,
                      files_checked=len(normalized),
                      diagnostics=["no window computable; advisory pass"])

    interv = intervening_commits(baseline.window_sha, head, normalized, repo_root=root)
    report = Report(status="clean", baseline=baseline, mode=mode, head=head,
                    files_checked=len(normalized), window_paths=len(interv))
    if baseline.detail:
        report.diagnostics.append(baseline.detail)
    if not interv:
        return report

    candidate_paths = sorted(interv)
    proposed = proposed_oids(candidate_paths, mode=mode, repo_root=root,
                             index_file=index_file, head=head)
    specs: "list[str]" = []
    for path in candidate_paths:
        specs.append(f"{interv[path]}:{path}")
        specs.append(f"{interv[path]}^:{path}")
    blobs = _batch_check_oids(specs, repo_root=root)

    session_class_cache: "dict[str, bool]" = {}

    def _is_session_class(commit: str) -> bool:
        if baseline.session_sha is None:
            return False
        if commit not in session_class_cache:
            session_class_cache[commit] = _is_ancestor(
                baseline.session_sha, commit, repo_root=root,
            ) and commit != baseline.session_sha
        return session_class_cache[commit]

    for path in candidate_paths:
        commit = interv[path]
        prop = proposed.get(path)
        parent_oid = blobs.get(f"{commit}^:{path}")
        interv_oid = blobs.get(f"{commit}:{path}")
        if prop is None:
            continue  # proposed deletion: DGR-governed, never a finding here
        if parent_oid is None:
            continue  # created by the intervening commit: nothing older to revert to
        if prop != parent_oid or prop == interv_oid:
            continue
        finding_class = "session" if _is_session_class(commit) else "lookback"
        if content_prefix_session_only and path.startswith("content/") \
                and finding_class == "lookback":
            report.diagnostics.append(
                f"content path {path} matches a pre-session state (commit "
                f"{commit[:10]}) -- suppressed pending the content-scale replay "
                f"(plan D-A(ii))"
            )
            continue
        token = override_lookup(path) if override_lookup else None
        report.findings.append(Finding(
            path=path, intervening_commit=commit, proposed_oid=prop,
            parent_oid=parent_oid, intervening_oid=interv_oid,
            finding_class=finding_class,
            override_token_id=(token or {}).get("override_id") if token else None,
        ))

    if report.findings:
        report.status = "regression"
    return report


def format_text(report: Report, *, wide_findings: str = "warn") -> str:
    """Human rendering (the CLI's default), including the context line every
    consumer prints on PASS so each commit log states which window judged it."""
    b = report.baseline
    lines = [
        f"baseline: {(b.window_sha or 'none')[:12]} source={b.source} "
        f"session={(b.session_id or 'none')} head={report.head[:12]} "
        f"mode={report.mode} checked={report.files_checked} "
        f"intervening={report.window_paths}"
    ]
    blocking = {id(f) for f in report.blocking(wide_findings=wide_findings)}
    for f in report.findings:
        marker = "BLOCK" if id(f) in blocking else (
            "ALLOW(token)" if f.override_token_id else "WARN(lookback)")
        lines.append(f"  {f.path}")
        lines.append(
            f"    [{marker}] matches the state BEFORE commit "
            f"{f.intervening_commit[:10]} ({f.finding_class} window)"
            + (f"; permitted by override token {f.override_token_id}"
               if f.override_token_id else "")
        )
    for d in report.diagnostics:
        lines.append(f"  note: {d}")
    return "\n".join(lines)
