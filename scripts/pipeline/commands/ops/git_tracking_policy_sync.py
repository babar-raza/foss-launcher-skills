#!/usr/bin/env python
"""git_tracking_policy_sync.py -- generate/verify the managed .gitignore block that
carves selectively-tracked subtrees out of an otherwise blanket-ignored root.

CONTRACT: scripts/pipeline/commands/ops/git_tracking_policy_sync.py
    purpose: reads scripts/pipeline/config/git_tracking_policy.yaml (declarative
        "default-ignore this root, track only these named children" policy) and
        renders the correct .gitignore negation chain for it. Un-ignoring a path under
        an ignored directory requires un-ignoring every ancestor level
        (`dir/*` + `!dir/sub/`, repeated down to the target) -- hand-written, this is a
        well-known git footgun that fails SILENTLY (the negation is simply a no-op) when
        a level is missed. This module makes that construction mechanical instead of
        hand-typed, and re-derives its "keep" name sets (e.g. Aspose family names) from
        their one canonical source on every run, so the .gitignore block can never drift
        from that source the way a hand-copied list would.
    sibling: scripts/pipeline/config/knowledge_tracking_policy.yaml solves the
        MIRROR-IMAGE problem (default-track a root, selectively DROP named subpaths, for
        knowledge/) via scripts/pipeline/commands/ops/knowledge_git_migration.py, which
        deliberately does NOT generate .gitignore from policy -- it keeps .gitignore
        hand-synced, to stay reviewable in a normal diff. That's the right call there:
        its drop_patterns are flat single-line ignores with no ancestor-chain gotcha.
        This module's direction is the opposite (default-ignore, selectively KEEP), and
        DOES generate the .gitignore block, because the ancestor-chain construction is
        exactly the error-prone part worth automating -- not the part worth hand-review.
    modes:
        --check   Recompute the expected block from policy; diff it against the
                  currently marked block in .gitignore (BEGIN/END GIT-TRACKING-POLICY
                  markers). Exit 1 with a unified diff on drift, 0 if clean.
        --fix     Recompute the expected block and write it into .gitignore in place,
                  removing any old marked block and any now-redundant bare top-level
                  ignore line (e.g. a standalone `reports/`) for each policy root's first
                  path segment -- that bare form is a DIRECTORY match, and git refuses to
                  re-include anything below an ignored directory no matter what negation
                  patterns follow it elsewhere in the file, so it must be replaced (with
                  `{root}/*`, a file-list match that permits descent) rather than merely
                  supplemented.
    fail-closed: a policy root whose keep set resolves to zero names still renders a
        valid, effectively-empty-exception block (root stays fully ignored) -- never an
        error, never a silent "track everything" fallback.
    policy types: `family_glob`/`literal` (under a `keep:` list) both assume a small,
        stable, enumerable name set with one canonical source -- fine for e.g. Aspose
        family names, wrong for a root whose children are unbounded and grow over time
        (e.g. `reports/plan_state/{mission-id}/`, one new directory per mission; added
        TC-GOV-01-01, 2026-09-17). For that shape, declare `type: whole_subtree` on the
        policy instead of a `keep:` list -- it tracks the entire root wholesale
        (`!{root}/`, no per-name enumeration), which is exactly git's own semantics for
        un-ignoring a directory: everything beneath it is tracked unless a nested
        pattern re-excludes something, and this module deliberately never emits one for
        a whole_subtree root. See resolve_keep_names() and render_merged_tree().
    tests: scripts/pipeline/tests/test_git_tracking_policy_sync.py
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import yaml

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]

_cfg_repo_root: Path = _DEFAULT_REPO_ROOT
_cfg_policy_path: Path = _DEFAULT_REPO_ROOT / "scripts/pipeline/config/git_tracking_policy.yaml"
_cfg_gitignore_path: Path = _DEFAULT_REPO_ROOT / ".gitignore"


def configure(
    *,
    repo_root: "Path | str | None" = None,
    policy_path: "Path | str | None" = None,
    gitignore_path: "Path | str | None" = None,
) -> None:
    """Test/CLI seam -- override module-level path constants (never monkeypatch these
    directly; this is the one supported way to redirect the module at a fixture)."""
    global _cfg_repo_root, _cfg_policy_path, _cfg_gitignore_path
    if repo_root is not None:
        _cfg_repo_root = Path(repo_root)
    if policy_path is not None:
        _cfg_policy_path = Path(policy_path)
    if gitignore_path is not None:
        _cfg_gitignore_path = Path(gitignore_path)


BEGIN_MARKER = "# BEGIN GIT-TRACKING-POLICY"
END_MARKER = "# END GIT-TRACKING-POLICY"

_HEADER_LINES = [
    f"{BEGIN_MARKER} (generated by",
    "# scripts/pipeline/commands/ops/git_tracking_policy_sync.py --fix, from",
    "# scripts/pipeline/config/git_tracking_policy.yaml -- do not hand-edit this block;",
    "# edit the policy file and rerun --fix.)",
]
_FOOTER_LINES = [END_MARKER]


def render_block(root: str, keep_names: "list[str]") -> "list[str]":
    """Render the .gitignore negation chain that ignores everything under `root` except
    each name in `keep_names` (tracked recursively). Pure function -- no I/O.

    For root="a/b/c" and keep_names=["x", "y"]:
        a/*
        !a/b/
        a/b/*
        !a/b/c/
        a/b/c/*
        !a/b/c/x/
        !a/b/c/y/
    """
    segments = root.split("/")
    lines = [f"{segments[0]}/*"]
    prefix = segments[0]
    for seg in segments[1:]:
        prefix = f"{prefix}/{seg}"
        lines.append(f"!{prefix}/")
        lines.append(f"{prefix}/*")
    lines.extend(f"!{prefix}/{name}/" for name in keep_names)
    return lines


def resolve_keep_names(policy: dict, repo_root: Path) -> "list[str] | None":
    """Resolve a policy entry's `keep` list to a sorted, de-duplicated name list.

    A policy declared `type: whole_subtree` (TC-GOV-01-01, 2026-09-17) tracks its
    entire root wholesale -- no per-name enumeration, no `keep:` list to resolve at
    all. This is for roots whose children are unbounded and grow over time (e.g.
    `reports/plan_state/{mission-id}/`, one new directory per mission), unlike
    `family_glob`/`literal`, which both assume a small, stable, enumerable name set
    with one canonical source. Returns None as the explicit "no enumerable name set"
    sentinel for that case -- deliberately NOT an empty list, which already has a
    different, incompatible meaning under this module's fail-closed contract (see
    render_block()'s test_empty_keep_set_still_ignores_everything: an empty keep list
    means "track nothing", the opposite of what whole_subtree means). Callers
    (build_full_block()/render_merged_tree(), list_tracked_prefixes()) branch on
    `is None` to skip the per-name model entirely for this policy type.
    """
    if policy.get("type") == "whole_subtree":
        if "keep" in policy:
            raise ValueError(
                f"policy root {policy.get('root')!r}: type 'whole_subtree' tracks its "
                f"entire root wholesale and does not take a 'keep' list -- remove "
                f"'keep' (it would be silently ignored) or drop 'type: whole_subtree' "
                f"if per-name enumeration was actually intended"
            )
        return None
    names: "set[str]" = set()
    for entry in policy.get("keep", []):
        entry_type = entry.get("type")
        if entry_type == "family_glob":
            source = repo_root / entry["source"]
            with open(source, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            names.update((data.get("families") or {}).keys())
        elif entry_type == "literal":
            names.update(entry.get("names", []))
        else:
            raise ValueError(
                f"policy root {policy.get('root')!r}: unknown keep entry type {entry_type!r}"
            )
    return sorted(names)


def render_merged_tree(root_keep: "dict[tuple[str, ...], list[str] | None]") -> "list[str]":
    """Render the ancestor-chain negation for MULTIPLE roots at once,
    merging any shared path-segment prefixes into ONE blanket `{prefix}/*`
    exclusion instead of one per root.

    PKGINSTALL-DEFECT-SWEEP-REDESIGN (2026-09-10): found live while adding a
    second reports/-rooted policy (reports/audit, alongside the pre-existing
    reports/repo-presenter-regen-full) -- build_full_block() used to call
    render_block() independently per policy, each emitting its OWN
    `reports/*` blanket-exclusion line. Git's negation semantics are
    last-match-wins across the WHOLE file: the SECOND policy's `reports/*`
    re-excludes everything the FIRST policy had already un-ignored,
    silently breaking that policy's tracking. Confirmed via real
    `git check-ignore -v` before this fix, not assumed -- see
    TestRealGitCheckIgnore's new two-sibling-policy case.

    Any two (or more) roots sharing a common ancestor prefix, at ANY depth,
    are handled the same way -- not just the "both start with reports/"
    case this bug was found through.

    TC-PKG-01-08-FIX (2026-09-17): fixed a second, independently-found
    defect in this same function -- a policy root that is ITSELF a
    path-prefix ancestor of another policy root (e.g. a policy at
    "reports/audit" alongside a separate, deeper policy at
    "reports/audit/install-defect-sweep") used to have the deeper root
    silently DROPPED from the output entirely, with zero error and zero
    warning. Root cause: the old walk() treated "this node is a policy root
    with its own keep names" and "this node has further policy-root
    descendants" as mutually exclusive (`if child_path in root_keep: ...
    elif child_path in children_of: walk(child_path)`) -- a node that is
    legitimately BOTH (the nested case) took the `if` branch and never
    recursed into its own children. render_node() below always renders a
    node's own keep names (if it is a policy root) AND recurses into any
    further policy-root descendants (if it is also an ancestor) -- the two
    are independent, not exclusive. Confirmed via real `git check-ignore -v`
    before this fix (not assumed) -- see
    TestRealGitCheckIgnoreNestedPolicyRoot.

    TC-GOV-01-01 (2026-09-17): a policy root's value in `root_keep` may now be
    None instead of a name list -- the `type: whole_subtree` sentinel from
    resolve_keep_names() (see its docstring), for roots whose children are
    unbounded and grow over time rather than being drawn from a small,
    enumerable set. For such a root, render_node() deliberately does NOT emit
    the `{path}/*` re-exclusion line at all: the parent level already un-ignores
    the directory itself (`!{parent}/{name}/`), and per git's own last-match-
    wins negation semantics, un-ignoring a directory tracks its full contents
    UNLESS a later, more specific pattern re-excludes something -- emitting
    `{path}/*` here would be exactly that re-exclusion, degrading whole_subtree
    to the empty-keep-set fail-closed case (tracking nothing). This holds
    regardless of where the whole_subtree root sits in the tree -- as a leaf,
    as a sibling of keep-type roots sharing an ancestor prefix, or nested
    directly under (or as the ancestor of) a keep-type root -- confirmed via
    real `git check-ignore -v` for all three shapes, not assumed -- see
    TestRealGitCheckIgnoreWholeSubtree and
    TestRealGitCheckIgnoreWholeSubtreeNestedUnderKeepType.
    """
    children_of: "dict[tuple[str, ...], set[str]]" = {}
    for segments in root_keep:
        for depth in range(len(segments)):
            parent = segments[:depth]
            children_of.setdefault(parent, set()).add(segments[depth])

    lines: "list[str]" = []

    def render_node(path: "tuple[str, ...]") -> None:
        """Render `path`'s own re-exclusion (if it is a keep-type root; a
        whole_subtree root emits none, see module docstring above) plus every
        negation needed directly under it, then recurse into any further
        policy-root descendants. `path` may be a plain ancestor segment
        (neither a policy root nor holding keep names of its own), a
        policy-root leaf (in root_keep, no deeper descendants), or -- the
        nested case TC-PKG-01-08-FIX addresses -- BOTH a policy root AND an
        ancestor of a deeper policy root at the same time.
        """
        path_str = "/".join(path)
        is_whole_subtree = path in root_keep and root_keep[path] is None
        nested_children = sorted(children_of.get(path, set()))

        if is_whole_subtree:
            # No `{path}/*` blanket here by design (see docstring) -- the
            # directory is already un-ignored by the caller and nothing here
            # may re-exclude any part of it. Any further nested policy root
            # declared underneath is still honored (opened explicitly and
            # recursed into), though ordinarily redundant since everything
            # here is already tracked.
            for child in nested_children:
                child_path = path + (child,)
                lines.append(f"!{path_str}/{child}/")
                render_node(child_path)
            return

        lines.append(f"{path_str}/*")
        own_names = sorted(root_keep[path]) if path in root_keep else []
        for name in sorted(set(nested_children) | set(own_names)):
            lines.append(f"!{path_str}/{name}/")
        for child in nested_children:
            child_path = path + (child,)
            if child_path in root_keep:
                keep_names = root_keep[child_path]
                child_str = "/".join(child_path)
                if keep_names is None:
                    lines.append(f"# {child_str} -- whole subtree tracked")
                else:
                    lines.append(f"# {child_str} -- {len(keep_names)} tracked name(s)")
            render_node(child_path)

    for top_segment in sorted({segments[0] for segments in root_keep}):
        render_node((top_segment,))
    return lines


def build_full_block(policies: "list[dict]", repo_root: Path) -> "list[str]":
    """Render the complete managed .gitignore block for every policy entry,
    with shared root prefixes merged into one collision-safe negation chain
    (see render_merged_tree())."""
    root_keep = {
        tuple(policy["root"].split("/")): resolve_keep_names(policy, repo_root)
        for policy in policies
    }
    lines = list(_HEADER_LINES)
    lines.extend(render_merged_tree(root_keep))
    lines.extend(_FOOTER_LINES)
    return lines


def load_policy(policy_path: Path) -> dict:
    with open(policy_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _read_gitignore_lines(gitignore_path: Path) -> "list[str]":
    if not gitignore_path.exists():
        return []
    with open(gitignore_path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    return text.replace("\r\n", "\n").split("\n")


def _write_gitignore_lines(gitignore_path: Path, lines: "list[str]") -> None:
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    with open(gitignore_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def extract_managed_block(lines: "list[str]") -> "list[str] | None":
    """Return the lines strictly between (and including) the BEGIN/END markers, or
    None if no marked block is present."""
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(BEGIN_MARKER):
            start = i
            break
    if start is None:
        return None
    for j in range(start, len(lines)):
        if lines[j].strip().startswith(END_MARKER):
            return lines[start : j + 1]
    return None


def apply_to_gitignore(
    lines: "list[str]", policies: "list[dict]", repo_root: Path
) -> "list[str]":
    """Return `lines` with the managed block replaced (or inserted) and any now-
    redundant bare top-level ignore line for a policy root's first path segment removed.

    A bare `reports/` (or `reports`) line is a DIRECTORY match: git will not re-include
    anything below an ignored directory regardless of later `!` patterns, so it must be
    replaced with `reports/*` (a file-list match, which permits descent) rather than
    merely supplemented -- leaving it in place would silently make the generated
    negations no-ops.
    """
    top_segments = {p["root"].split("/")[0] for p in policies}
    new_block = build_full_block(policies, repo_root)

    out: "list[str]" = []
    insert_at: "int | None" = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith(BEGIN_MARKER):
            if insert_at is None:
                insert_at = len(out)
            i += 1
            while i < n and not lines[i].strip().startswith(END_MARKER):
                i += 1
            i += 1  # consume the END marker line too
            continue

        bare = stripped[:-1] if stripped.endswith("/") else stripped
        is_bare_top_segment = (
            bare in top_segments
            and "/" not in bare
            and not stripped.startswith("#")
        )
        if is_bare_top_segment:
            if insert_at is None:
                insert_at = len(out)
            i += 1
            continue

        out.append(line)
        i += 1

    if insert_at is None:
        insert_at = len(out)
        if out and out[-1].strip() != "":
            out.append("")
    out[insert_at:insert_at] = new_block
    return out


def list_tracked_prefixes(policies: "list[dict]", repo_root: Path) -> "list[str]":
    """Return every prefix current policy permits to be tracked, e.g.
    `reports/repo-presenter-regen-full/cells/`. Consumed by scripts/pre-commit-audit.sh's
    "reports/ boundary" gate (Step 1) so that gate's blanket "nothing under reports/ may
    ever be staged" rule can carve out exactly (and only) what this policy allows, instead
    of either blocking every policy-tracked commit or being disabled wholesale.

    A `type: whole_subtree` policy (TC-GOV-01-01) has no per-name set to resolve --
    resolve_keep_names() returns None for it -- so the one prefix it permits is the
    root itself (`{root}/`), covering everything beneath it, rather than a `{root}/{name}/`
    line per enumerated name.
    """
    prefixes: "list[str]" = []
    for policy in policies:
        root = policy["root"]
        names = resolve_keep_names(policy, repo_root)
        if names is None:
            prefixes.append(f"{root}/")
        else:
            for name in names:
                prefixes.append(f"{root}/{name}/")
    return prefixes


def cmd_list_tracked_prefixes(args: argparse.Namespace) -> int:
    policy = load_policy(_cfg_policy_path)
    policies = policy.get("policies", [])
    for prefix in list_tracked_prefixes(policies, _cfg_repo_root):
        print(prefix)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    policy = load_policy(_cfg_policy_path)
    policies = policy.get("policies", [])
    expected = build_full_block(policies, _cfg_repo_root)
    current_lines = _read_gitignore_lines(_cfg_gitignore_path)
    actual = extract_managed_block(current_lines)

    if actual == expected:
        print(
            f"git-tracking-policy: OK -- {_cfg_gitignore_path} matches "
            f"{_cfg_policy_path} ({len(policies)} policy root(s))"
        )
        return 0

    print(
        f"git-tracking-policy: DRIFT -- {_cfg_gitignore_path} does not match "
        f"{_cfg_policy_path}",
        file=sys.stderr,
    )
    diff = difflib.unified_diff(
        actual if actual is not None else [],
        expected,
        fromfile="gitignore (current)",
        tofile="policy (expected)",
        lineterm="",
    )
    for line in diff:
        print(line, file=sys.stderr)
    print(
        "\nFix with: PYTHONPATH=scripts/pipeline .venv/Scripts/python "
        "scripts/pipeline/commands/ops/git_tracking_policy_sync.py --fix",
        file=sys.stderr,
    )
    return 1


def cmd_fix(args: argparse.Namespace) -> int:
    policy = load_policy(_cfg_policy_path)
    policies = policy.get("policies", [])
    current_lines = _read_gitignore_lines(_cfg_gitignore_path)
    new_lines = apply_to_gitignore(current_lines, policies, _cfg_repo_root)
    _write_gitignore_lines(_cfg_gitignore_path, new_lines)
    print(
        f"git-tracking-policy: wrote {len(policies)} policy block(s) to "
        f"{_cfg_gitignore_path}"
    )
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="git_tracking_policy_sync",
        description=(
            "Generate/verify the managed .gitignore block for "
            "scripts/pipeline/config/git_tracking_policy.yaml."
        ),
    )
    parser.add_argument("--repo-root", help="Override repo root (default: auto-detected)")
    parser.add_argument("--policy", help="Override policy YAML path")
    parser.add_argument("--gitignore", help="Override .gitignore path")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Verify .gitignore matches policy")
    mode.add_argument("--fix", action="store_true", help="Write policy-derived block to .gitignore")
    mode.add_argument("--list-tracked-prefixes", action="store_true",
                       help="Print every {root}/{name}/ prefix current policy permits to be tracked")
    args = parser.parse_args(argv)

    configure(repo_root=args.repo_root, policy_path=args.policy, gitignore_path=args.gitignore)

    if args.check:
        return cmd_check(args)
    if args.list_tracked_prefixes:
        return cmd_list_tracked_prefixes(args)
    return cmd_fix(args)


if __name__ == "__main__":
    sys.exit(main())
