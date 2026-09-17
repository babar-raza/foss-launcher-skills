"""Tests for git_tracking_policy_sync.py -- the .gitignore negation-chain generator
that carves selectively-tracked subtrees out of an otherwise blanket-ignored root.
"""

import subprocess
import textwrap

import pytest
import yaml

import git_tracking_policy_sync as gtp


# ---------------------------------------------------------------------------
# render_block -- the ancestor-chain algorithm itself
# ---------------------------------------------------------------------------

class TestRenderBlock:
    def test_single_segment_root(self):
        assert gtp.render_block("reports", ["cells", "pdf"]) == [
            "reports/*",
            "!reports/cells/",
            "!reports/pdf/",
        ]

    def test_multi_segment_root_chains_every_ancestor(self):
        lines = gtp.render_block("reports/repo-presenter-regen-full", ["cells"])
        assert lines == [
            "reports/*",
            "!reports/repo-presenter-regen-full/",
            "reports/repo-presenter-regen-full/*",
            "!reports/repo-presenter-regen-full/cells/",
        ]

    def test_deeper_root_chains_every_level(self):
        lines = gtp.render_block("a/b/c", ["x", "y"])
        assert lines == [
            "a/*",
            "!a/b/",
            "a/b/*",
            "!a/b/c/",
            "a/b/c/*",
            "!a/b/c/x/",
            "!a/b/c/y/",
        ]

    def test_empty_keep_set_still_ignores_everything(self):
        lines = gtp.render_block("reports/foo", [])
        assert lines == ["reports/*", "!reports/foo/", "reports/foo/*"]

    def test_idempotent(self):
        first = gtp.render_block("reports/repo-presenter-regen-full", ["cells", "pdf"])
        second = gtp.render_block("reports/repo-presenter-regen-full", ["cells", "pdf"])
        assert first == second


# ---------------------------------------------------------------------------
# resolve_keep_names / build_full_block
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_families_yaml(tmp_path):
    path = tmp_path / "data" / "fake_family_routes.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(
            """\
            families:
              zebra:
                taxonomy_slug: "aspose.zebra"
              alpha:
                taxonomy_slug: "aspose.alpha"
            """
        ),
        encoding="utf-8",
    )
    return tmp_path


class TestResolveKeepNames:
    def test_family_glob_resolves_sorted_names(self, fake_families_yaml):
        policy = {
            "root": "reports/x",
            "keep": [{"type": "family_glob", "source": "data/fake_family_routes.yaml"}],
        }
        assert gtp.resolve_keep_names(policy, fake_families_yaml) == ["alpha", "zebra"]

    def test_literal_names(self, tmp_path):
        policy = {"root": "reports/x", "keep": [{"type": "literal", "names": ["b", "a"]}]}
        assert gtp.resolve_keep_names(policy, tmp_path) == ["a", "b"]

    def test_unknown_type_raises(self, tmp_path):
        policy = {"root": "reports/x", "keep": [{"type": "bogus"}]}
        with pytest.raises(ValueError):
            gtp.resolve_keep_names(policy, tmp_path)

    def test_whole_subtree_returns_none_sentinel(self, tmp_path):
        """A `type: whole_subtree` policy has no `keep:` list to resolve at all --
        it tracks its entire root wholesale. None is the explicit "no enumerable
        name set" sentinel here, distinct from an empty list (which means "keep
        nothing" under the existing fail-closed contract -- see
        test_empty_keep_set_still_ignores_everything in TestRenderBlock)."""
        policy = {"root": "reports/plan_state", "type": "whole_subtree"}
        assert gtp.resolve_keep_names(policy, tmp_path) is None

    def test_whole_subtree_with_keep_list_raises(self, tmp_path):
        """`type: whole_subtree` and `keep:` are mutually exclusive -- a policy
        author who adds a `keep:` list to a whole_subtree root almost certainly
        means the opposite of what will happen (the keep list would be silently
        ignored otherwise), so this fails loudly instead."""
        policy = {
            "root": "reports/plan_state",
            "type": "whole_subtree",
            "keep": [{"type": "literal", "names": ["x"]}],
        }
        with pytest.raises(ValueError):
            gtp.resolve_keep_names(policy, tmp_path)


class TestListTrackedPrefixes:
    def test_returns_root_name_prefixes(self, fake_families_yaml):
        policies = [
            {
                "root": "reports/repo-presenter-regen-full",
                "keep": [{"type": "family_glob", "source": "data/fake_family_routes.yaml"}],
            }
        ]
        prefixes = gtp.list_tracked_prefixes(policies, fake_families_yaml)
        assert prefixes == [
            "reports/repo-presenter-regen-full/alpha/",
            "reports/repo-presenter-regen-full/zebra/",
        ]

    def test_cli_mode_prints_one_per_line(self, policy_repo, capsys):
        assert gtp.main(["--list-tracked-prefixes"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert "reports/repo-presenter-regen-full/cells/" in out
        assert "reports/repo-presenter-regen-full/pdf/" in out

    def test_whole_subtree_returns_root_prefix_not_per_name(self, tmp_path):
        """A whole_subtree policy has no enumerable name set -- the one prefix
        it permits the reports/ boundary gate to carve out is the root itself,
        not a per-name list."""
        policies = [{"root": "reports/plan_state", "type": "whole_subtree"}]
        prefixes = gtp.list_tracked_prefixes(policies, tmp_path)
        assert prefixes == ["reports/plan_state/"]


class TestBuildFullBlock:
    def test_wraps_with_markers(self, fake_families_yaml):
        policies = [
            {
                "root": "reports/repo-presenter-regen-full",
                "keep": [{"type": "family_glob", "source": "data/fake_family_routes.yaml"}],
            }
        ]
        block = gtp.build_full_block(policies, fake_families_yaml)
        assert block[0].startswith(gtp.BEGIN_MARKER)
        assert block[-1] == gtp.END_MARKER
        assert "!reports/repo-presenter-regen-full/alpha/" in block
        assert "!reports/repo-presenter-regen-full/zebra/" in block


# ---------------------------------------------------------------------------
# apply_to_gitignore -- bare-line removal + block insertion/replacement
# ---------------------------------------------------------------------------

class TestApplyToGitignore:
    def test_removes_bare_top_segment_line(self, fake_families_yaml):
        original = ["node_modules", "reports/", "*.pyc"]
        policies = [
            {
                "root": "reports/repo-presenter-regen-full",
                "keep": [{"type": "family_glob", "source": "data/fake_family_routes.yaml"}],
            }
        ]
        result = gtp.apply_to_gitignore(original, policies, fake_families_yaml)
        assert "reports/" not in result
        assert "node_modules" in result
        assert "*.pyc" in result
        assert any(line.startswith(gtp.BEGIN_MARKER) for line in result)

    def test_does_not_touch_unrelated_nested_rule(self, fake_families_yaml):
        # reports/incidents/ is a MORE SPECIFIC rule, not the bare top-segment line --
        # must survive untouched even though it starts with "reports".
        original = ["reports/incidents/", "reports/"]
        policies = [
            {
                "root": "reports/repo-presenter-regen-full",
                "keep": [{"type": "family_glob", "source": "data/fake_family_routes.yaml"}],
            }
        ]
        result = gtp.apply_to_gitignore(original, policies, fake_families_yaml)
        assert "reports/incidents/" in result

    def test_second_fix_replaces_prior_block_in_place(self, fake_families_yaml):
        original = ["node_modules", "reports/"]
        policies = [
            {
                "root": "reports/repo-presenter-regen-full",
                "keep": [{"type": "family_glob", "source": "data/fake_family_routes.yaml"}],
            }
        ]
        once = gtp.apply_to_gitignore(original, policies, fake_families_yaml)
        twice = gtp.apply_to_gitignore(once, policies, fake_families_yaml)
        assert once == twice
        assert sum(1 for line in twice if line.startswith(gtp.BEGIN_MARKER)) == 1


# ---------------------------------------------------------------------------
# --check / --fix CLI, via configure() seam
# ---------------------------------------------------------------------------

@pytest.fixture
def policy_repo(tmp_path):
    """A minimal on-disk repo layout: policy yaml + family routes yaml + .gitignore."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "blog_family_routes.yaml").write_text(
        "families:\n  cells:\n    taxonomy_slug: aspose.cells\n  pdf:\n    taxonomy_slug: aspose.pdf\n",
        encoding="utf-8",
    )
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        textwrap.dedent(
            """\
            schema_version: 1
            policies:
              - root: reports/repo-presenter-regen-full
                keep:
                  - type: family_glob
                    source: data/blog_family_routes.yaml
            """
        ),
        encoding="utf-8",
    )
    gitignore_path = tmp_path / ".gitignore"
    gitignore_path.write_text("node_modules\nreports/\n*.pyc\n", encoding="utf-8")
    gtp.configure(repo_root=tmp_path, policy_path=policy_path, gitignore_path=gitignore_path)
    yield tmp_path, policy_path, gitignore_path
    gtp.configure(
        repo_root=gtp._DEFAULT_REPO_ROOT,
        policy_path=gtp._DEFAULT_REPO_ROOT / "scripts/pipeline/config/git_tracking_policy.yaml",
        gitignore_path=gtp._DEFAULT_REPO_ROOT / ".gitignore",
    )


class TestCheckFixCLI:
    def test_check_fails_before_fix(self, policy_repo, capsys):
        assert gtp.main(["--check"]) == 1

    def test_fix_then_check_is_clean(self, policy_repo, capsys):
        _, _, gitignore_path = policy_repo
        assert gtp.main(["--fix"]) == 0
        assert gtp.main(["--check"]) == 0
        text = gitignore_path.read_text(encoding="utf-8")
        assert "reports/*" in text
        assert "!reports/repo-presenter-regen-full/cells/" in text
        assert "!reports/repo-presenter-regen-full/pdf/" in text
        # bare directory-match form must be gone, not merely supplemented
        assert "\nreports/\n" not in ("\n" + text)

    def test_fix_is_idempotent(self, policy_repo):
        assert gtp.main(["--fix"]) == 0
        first = (policy_repo[2]).read_text(encoding="utf-8")
        assert gtp.main(["--fix"]) == 0
        second = (policy_repo[2]).read_text(encoding="utf-8")
        assert first == second

    def test_check_detects_drift_after_manual_edit(self, policy_repo):
        _, _, gitignore_path = policy_repo
        assert gtp.main(["--fix"]) == 0
        gitignore_path.write_text(
            gitignore_path.read_text(encoding="utf-8") + "\nextra-drift-line\n",
            encoding="utf-8",
        )
        assert gtp.main(["--check"]) == 0  # extra line outside markers is irrelevant

        # Now corrupt the managed block itself -- this must be caught.
        corrupted = gitignore_path.read_text(encoding="utf-8").replace(
            "!reports/repo-presenter-regen-full/cells/", "!reports/repo-presenter-regen-full/CELLS/"
        )
        gitignore_path.write_text(corrupted, encoding="utf-8")
        assert gtp.main(["--check"]) == 1


# ---------------------------------------------------------------------------
# Real `git check-ignore` integration -- the actual regression control, not just
# string assertions. Proves the generated block behaves correctly under real git
# semantics, in both directions, including the ancestor-chain gotcha this module
# exists to eliminate.
# ---------------------------------------------------------------------------

def _git_check_ignore(repo_dir, rel_path) -> bool:
    """True if `rel_path` is ignored according to real git, inside `repo_dir`."""
    (repo_dir / rel_path).parent.mkdir(parents=True, exist_ok=True)
    (repo_dir / rel_path).write_text("x", encoding="utf-8")
    result = subprocess.run(
        ["git", "check-ignore", "-q", rel_path],
        cwd=str(repo_dir),
        capture_output=True,
    )
    return result.returncode == 0


class TestRealGitCheckIgnore:
    @pytest.fixture(autouse=True)
    def _init_repo(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "blog_family_routes.yaml").write_text(
            "families:\n  cells:\n    taxonomy_slug: aspose.cells\n"
            "  pdf:\n    taxonomy_slug: aspose.pdf\n",
            encoding="utf-8",
        )
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(
            textwrap.dedent(
                """\
                schema_version: 1
                policies:
                  - root: reports/repo-presenter-regen-full
                    keep:
                      - type: family_glob
                        source: data/blog_family_routes.yaml
                """
            ),
            encoding="utf-8",
        )
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("node_modules\nreports/\n*.pyc\n", encoding="utf-8")
        gtp.configure(repo_root=tmp_path, policy_path=policy_path, gitignore_path=gitignore_path)
        assert gtp.main(["--fix"]) == 0
        self.repo = tmp_path
        yield
        gtp.configure(
            repo_root=gtp._DEFAULT_REPO_ROOT,
            policy_path=gtp._DEFAULT_REPO_ROOT / "scripts/pipeline/config/git_tracking_policy.yaml",
            gitignore_path=gtp._DEFAULT_REPO_ROOT / ".gitignore",
        )

    def test_family_content_is_tracked(self):
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/cells/java/readme.md") is False

    def test_family_with_no_dir_yet_is_still_tracked(self):
        # "pdf" has no directory on disk in this fixture yet -- policy still covers it.
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/pdf/readme.md") is False

    def test_non_family_sibling_stays_ignored(self):
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/_scratch/x.json") is True

    def test_loose_files_at_regen_full_root_stay_ignored(self):
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/_briefing.md") is True

    def test_different_top_level_family_tree_stays_ignored(self):
        # reports/cells/ (a DIFFERENT tree than reports/repo-presenter-regen-full/cells/)
        # must NOT be accidentally un-ignored.
        assert _git_check_ignore(self.repo, "reports/cells/some-file.md") is True

    def test_unrelated_report_dir_stays_ignored(self):
        assert _git_check_ignore(self.repo, "reports/some-other-report/x.md") is True


# ---------------------------------------------------------------------------
# render_merged_tree -- multi-policy shared-prefix collision fix
# (PKGINSTALL-DEFECT-SWEEP-REDESIGN, 2026-09-10)
# ---------------------------------------------------------------------------

class TestRenderMergedTree:
    def test_two_roots_sharing_a_top_segment_emit_one_shared_blanket_line(self):
        root_keep = {
            ("reports", "audit"): ["install-defect-sweep-latest"],
            ("reports", "repo-presenter-regen-full"): ["cells", "pdf"],
        }
        lines = gtp.render_merged_tree(root_keep)
        assert lines.count("reports/*") == 1, "must not re-declare the shared blanket exclusion twice"
        assert "!reports/audit/" in lines
        assert "!reports/repo-presenter-regen-full/" in lines
        assert "!reports/audit/install-defect-sweep-latest/" in lines
        assert "!reports/repo-presenter-regen-full/cells/" in lines
        assert "!reports/repo-presenter-regen-full/pdf/" in lines

    def test_ordering_the_shared_ancestor_negations_precede_both_leaf_blocks(self):
        """Both siblings' `!reports/{name}/` negations must appear BEFORE
        either leaf's own `reports/{name}/*` re-exclusion -- git evaluates
        patterns in file order, so getting this backwards would silently
        reproduce the original bug for whichever sibling comes second."""
        root_keep = {
            ("reports", "audit"): ["x"],
            ("reports", "repo-presenter-regen-full"): ["cells"],
        }
        lines = gtp.render_merged_tree(root_keep)
        i_blanket = lines.index("reports/*")
        i_negate_audit = lines.index("!reports/audit/")
        i_negate_repo_presenter = lines.index("!reports/repo-presenter-regen-full/")
        i_leaf_audit = lines.index("reports/audit/*")
        i_leaf_repo_presenter = lines.index("reports/repo-presenter-regen-full/*")
        assert i_blanket < i_negate_audit < i_leaf_audit
        assert i_blanket < i_negate_repo_presenter < i_leaf_repo_presenter

    def test_single_root_output_matches_render_block_exactly(self):
        """Backward-compat: with only one policy, the merged-tree output
        must be byte-identical to the old per-policy render_block() path
        (modulo the now-inline comment line) -- no regression for the
        pre-existing single-policy case."""
        root_keep = {("reports", "repo-presenter-regen-full"): ["cells", "pdf"]}
        merged = [l for l in gtp.render_merged_tree(root_keep) if not l.startswith("#")]
        assert merged == gtp.render_block("reports/repo-presenter-regen-full", ["cells", "pdf"])

    def test_nested_root_that_is_also_an_ancestor_of_another_root_is_not_dropped(self):
        """TC-PKG-01-08-FIX (2026-09-17): a real, previously-untested defect
        found reviewing TC-PKG-01-08 -- when one policy root is ITSELF a
        path-prefix ancestor of another policy root (e.g. 'reports/audit'
        holding its own tracked names, with a SEPARATE deeper policy at
        'reports/audit/install-defect-sweep'), the deeper root used to be
        silently dropped from the output entirely: zero error, zero warning.

        Root cause (in the pre-fix code): walk()'s
        `if child_path in root_keep: ... elif child_path in children_of: ...`
        treated "this node IS a policy root" and "this node has further
        descendants to walk" as mutually exclusive, so a node that is
        legitimately both never recursed into its own children.

        3 policies total, matching the taskcard's own brief: the 2
        pre-existing siblings already covered by TestRenderMergedTree above,
        PLUS a new policy that is a path-prefix ancestor of another policy
        ('reports/audit' <- ancestor of -> 'reports/audit/install-defect-sweep').
        """
        root_keep = {
            ("reports", "audit"): ["y"],
            ("reports", "audit", "install-defect-sweep"): ["z"],
            ("reports", "repo-presenter-regen-full"): ["cells", "pdf"],
        }
        lines = gtp.render_merged_tree(root_keep)

        # The ancestor root's OWN tracked name must still be negated.
        assert "!reports/audit/y/" in lines, (
            "ancestor policy root's own keep name must not be lost just "
            "because it is also an ancestor of a deeper policy root"
        )
        # The nested (deeper) root must not be silently dropped.
        assert "!reports/audit/install-defect-sweep/" in lines, (
            "must un-ignore the nested root's own directory so descent is possible"
        )
        assert "reports/audit/install-defect-sweep/*" in lines, (
            "must re-exclude everything under the nested root except its own keep names"
        )
        assert "!reports/audit/install-defect-sweep/z/" in lines, (
            "the nested root's own tracked name was the exact thing silently "
            "dropped by the pre-fix bug -- this is the regression control"
        )
        # The unrelated sibling policy must be completely unaffected.
        assert "!reports/repo-presenter-regen-full/cells/" in lines
        assert "!reports/repo-presenter-regen-full/pdf/" in lines
        # The shared top-level blanket exclusion still appears exactly once.
        assert lines.count("reports/*") == 1

        # Ordering: every "!.../x/" negation must appear strictly before the
        # "*" line it depends on being un-done for -- otherwise the negation
        # is a no-op under real git last-match-wins semantics (the same
        # ordering invariant TestRenderMergedTree already checks for siblings).
        i_blanket = lines.index("reports/*")
        i_negate_audit_dir = lines.index("!reports/audit/")
        i_audit_star = lines.index("reports/audit/*")
        i_negate_nested_dir = lines.index("!reports/audit/install-defect-sweep/")
        i_nested_star = lines.index("reports/audit/install-defect-sweep/*")
        i_negate_z = lines.index("!reports/audit/install-defect-sweep/z/")
        assert i_blanket < i_negate_audit_dir < i_audit_star
        assert i_audit_star < i_negate_nested_dir < i_nested_star
        assert i_nested_star < i_negate_z

    def test_whole_subtree_root_emits_bare_negation_no_blanket_reexclusion(self):
        """TC-GOV-01-01: a `type: whole_subtree` root (represented in root_keep
        by the value None -- see resolve_keep_names()) tracks everything beneath
        it. Unlike a keep-type root, it must NOT emit its own `{root}/*`
        re-exclusion line at all -- per git's own semantics, un-ignoring a
        directory (`!reports/plan_state/`) tracks its full contents unless a
        LATER, more specific pattern re-excludes something; emitting
        `reports/plan_state/*` would be exactly that re-exclusion, and would
        silently defeat the entire point of this policy type (it would degrade
        to the empty-keep-set fail-closed case, tracking nothing)."""
        root_keep = {("reports", "plan_state"): None}
        lines = gtp.render_merged_tree(root_keep)
        # The explanatory "# ... -- whole subtree tracked" comment line mirrors the
        # existing "# ... -- N tracked name(s)" comment keep-type children get (see
        # test_nested_root_that_is_also_an_ancestor_of_another_root_is_not_dropped
        # above) -- consistent readability, not a behavioral line.
        assert lines == [
            "reports/*",
            "!reports/plan_state/",
            "# reports/plan_state -- whole subtree tracked",
        ]
        assert "reports/plan_state/*" not in lines

    def test_whole_subtree_coexists_with_keep_type_siblings(self):
        """Mirrors TestRenderMergedTree's sibling-merge cases above, but with a
        third sibling declared whole_subtree -- proves the new type doesn't
        disturb the shared-blanket-exclusion merge for its family_glob/literal
        neighbors, and vice versa."""
        root_keep = {
            ("reports", "audit"): ["install-defect-sweep-latest"],
            ("reports", "repo-presenter-regen-full"): ["cells", "pdf"],
            ("reports", "plan_state"): None,
        }
        lines = gtp.render_merged_tree(root_keep)
        assert lines.count("reports/*") == 1
        assert "!reports/plan_state/" in lines
        assert "reports/plan_state/*" not in lines
        assert "!reports/audit/install-defect-sweep-latest/" in lines
        assert "reports/audit/*" in lines
        assert "!reports/repo-presenter-regen-full/cells/" in lines
        assert "!reports/repo-presenter-regen-full/pdf/" in lines
        assert "reports/repo-presenter-regen-full/*" in lines

    def test_whole_subtree_nested_under_keep_type_ancestor_is_not_reexcluded(self):
        """A whole_subtree root can itself be nested one level below a
        keep-type ancestor root -- e.g. reports/audit tracks one named child
        by 'keep', AND wholesale-tracks a further, unbounded subdirectory
        underneath it. The ancestor's own `reports/audit/*` re-exclusion (which
        it still needs, for its OWN keep-name enumeration) must not re-swallow
        the nested whole_subtree root -- the `!reports/audit/full-dump/`
        negation must come after it with nothing following to undo it."""
        root_keep = {
            ("reports", "audit"): ["y"],
            ("reports", "audit", "full-dump"): None,
        }
        lines = gtp.render_merged_tree(root_keep)
        assert "reports/audit/*" in lines
        assert "!reports/audit/y/" in lines
        assert "!reports/audit/full-dump/" in lines
        assert "reports/audit/full-dump/*" not in lines
        i_audit_star = lines.index("reports/audit/*")
        i_negate_full_dump = lines.index("!reports/audit/full-dump/")
        assert i_audit_star < i_negate_full_dump


class TestRealGitCheckIgnoreMultiPolicy:
    """The actual regression control for the collision this taskcard found
    live: 2 policies sharing 'reports/' as their first path segment used to
    silently break each other's tracking (confirmed via real
    `git check-ignore -v` before this fix -- not a hypothetical)."""

    @pytest.fixture(autouse=True)
    def _init_repo(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "blog_family_routes.yaml").write_text(
            "families:\n  cells:\n    taxonomy_slug: aspose.cells\n",
            encoding="utf-8",
        )
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(
            textwrap.dedent(
                """\
                schema_version: 1
                policies:
                  - root: reports/audit
                    keep:
                      - type: literal
                        names: ["install-defect-sweep-latest"]
                  - root: reports/repo-presenter-regen-full
                    keep:
                      - type: family_glob
                        source: data/blog_family_routes.yaml
                """
            ),
            encoding="utf-8",
        )
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("node_modules\nreports/\n*.pyc\n", encoding="utf-8")
        gtp.configure(repo_root=tmp_path, policy_path=policy_path, gitignore_path=gitignore_path)
        assert gtp.main(["--fix"]) == 0
        self.repo = tmp_path
        yield
        gtp.configure(
            repo_root=gtp._DEFAULT_REPO_ROOT,
            policy_path=gtp._DEFAULT_REPO_ROOT / "scripts/pipeline/config/git_tracking_policy.yaml",
            gitignore_path=gtp._DEFAULT_REPO_ROOT / ".gitignore",
        )

    def test_first_policys_tracked_path_is_not_ignored(self):
        assert _git_check_ignore(self.repo, "reports/audit/install-defect-sweep-latest/report.json") is False

    def test_second_policys_tracked_path_is_still_not_ignored(self):
        """This is the exact line that silently broke before the fix: the
        second policy's own render_block() call used to re-declare
        `reports/*`, undoing the first policy's negation for THIS path."""
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/cells/readme.md") is False

    def test_untracked_sibling_under_either_root_stays_ignored(self):
        assert _git_check_ignore(self.repo, "reports/audit/st054/sweep-report.json") is True
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/_scratch/x.md") is True


class TestRealGitCheckIgnoreNestedPolicyRoot:
    """The real regression control for the nested-root defect found
    reviewing TC-PKG-01-08: a policy root that is ITSELF a path-prefix
    ancestor of another policy root used to have the deeper root's entire
    keep block silently dropped from the generated .gitignore (confirmed
    live via real `git check-ignore -v` before the fix -- not a
    hypothetical). 3 policies: the 2 pre-existing siblings from
    TestRealGitCheckIgnoreMultiPolicy, PLUS a new policy nested one level
    below 'reports/audit'.
    """

    @pytest.fixture(autouse=True)
    def _init_repo(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "blog_family_routes.yaml").write_text(
            "families:\n  cells:\n    taxonomy_slug: aspose.cells\n",
            encoding="utf-8",
        )
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(
            textwrap.dedent(
                """\
                schema_version: 1
                policies:
                  - root: reports/audit
                    keep:
                      - type: literal
                        names: ["y"]
                  - root: reports/audit/install-defect-sweep
                    keep:
                      - type: literal
                        names: ["z"]
                  - root: reports/repo-presenter-regen-full
                    keep:
                      - type: family_glob
                        source: data/blog_family_routes.yaml
                """
            ),
            encoding="utf-8",
        )
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("node_modules\nreports/\n*.pyc\n", encoding="utf-8")
        gtp.configure(repo_root=tmp_path, policy_path=policy_path, gitignore_path=gitignore_path)
        assert gtp.main(["--fix"]) == 0
        self.repo = tmp_path
        yield
        gtp.configure(
            repo_root=gtp._DEFAULT_REPO_ROOT,
            policy_path=gtp._DEFAULT_REPO_ROOT / "scripts/pipeline/config/git_tracking_policy.yaml",
            gitignore_path=gtp._DEFAULT_REPO_ROOT / ".gitignore",
        )

    def test_ancestor_roots_own_tracked_name_is_not_ignored(self):
        assert _git_check_ignore(self.repo, "reports/audit/y/report.json") is False

    def test_nested_roots_tracked_name_is_not_ignored(self):
        """This is the exact path that was silently dropped before the fix:
        the deeper policy's own keep name never appeared anywhere in the
        generated .gitignore block, so it stayed ignored under the ancestor
        root's blanket re-exclusion with no negation to rescue it."""
        assert _git_check_ignore(
            self.repo, "reports/audit/install-defect-sweep/z/report.json"
        ) is False

    def test_untracked_sibling_under_nested_root_stays_ignored(self):
        assert _git_check_ignore(
            self.repo, "reports/audit/install-defect-sweep/other-file.json"
        ) is True

    def test_untracked_sibling_under_ancestor_root_stays_ignored(self):
        assert _git_check_ignore(self.repo, "reports/audit/st054/sweep-report.json") is True

    def test_unrelated_sibling_policy_still_works(self):
        assert _git_check_ignore(
            self.repo, "reports/repo-presenter-regen-full/cells/readme.md"
        ) is False
        assert _git_check_ignore(
            self.repo, "reports/repo-presenter-regen-full/_scratch/x.md"
        ) is True


# ---------------------------------------------------------------------------
# whole_subtree -- TC-GOV-01-01 (2026-09-17): tracks an entire root wholesale,
# with no per-name `keep:` enumeration, for roots whose children are unbounded
# and grow over time (e.g. reports/plan_state/{mission-id}/, one new directory
# per mission). Real regression control, mirroring TestRealGitCheckIgnore*
# above: proves via actual `git check-ignore -v` that EVERY path under the
# root is tracked, including nested subdirectories the policy never named --
# not just the specific paths a hand-picked assertion might happen to cover.
# ---------------------------------------------------------------------------

class TestRealGitCheckIgnoreWholeSubtree:
    """3 policies: the 2 pre-existing keep-type siblings from
    TestRealGitCheckIgnoreMultiPolicy, PLUS a new whole_subtree sibling
    (reports/plan_state) -- the exact shape of this taskcard's real
    scripts/pipeline/config/git_tracking_policy.yaml change."""

    @pytest.fixture(autouse=True)
    def _init_repo(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "blog_family_routes.yaml").write_text(
            "families:\n  cells:\n    taxonomy_slug: aspose.cells\n",
            encoding="utf-8",
        )
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(
            textwrap.dedent(
                """\
                schema_version: 1
                policies:
                  - root: reports/audit
                    keep:
                      - type: literal
                        names: ["install-defect-sweep-latest"]
                  - root: reports/repo-presenter-regen-full
                    keep:
                      - type: family_glob
                        source: data/blog_family_routes.yaml
                  - root: reports/plan_state
                    type: whole_subtree
                """
            ),
            encoding="utf-8",
        )
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("node_modules\nreports/\n*.pyc\n", encoding="utf-8")
        gtp.configure(repo_root=tmp_path, policy_path=policy_path, gitignore_path=gitignore_path)
        assert gtp.main(["--fix"]) == 0
        self.repo = tmp_path
        yield
        gtp.configure(
            repo_root=gtp._DEFAULT_REPO_ROOT,
            policy_path=gtp._DEFAULT_REPO_ROOT / "scripts/pipeline/config/git_tracking_policy.yaml",
            gitignore_path=gtp._DEFAULT_REPO_ROOT / ".gitignore",
        )

    def test_top_level_file_directly_under_root_is_tracked(self):
        assert _git_check_ignore(
            self.repo, "reports/plan_state/MT071-2026-09-17-GOVERNANCE-DURABILITY-HARDENING/taskcards.jsonl"
        ) is False

    def test_arbitrarily_deep_nested_subdirectory_never_named_is_still_tracked(self):
        """The whole point of whole_subtree: a mission directory nobody
        enumerated in policy, several levels deep, must still be tracked --
        this is what distinguishes it from family_glob/literal, which only
        track directories whose NAMES are registered somewhere."""
        assert _git_check_ignore(
            self.repo,
            "reports/plan_state/some-brand-new-mission-nobody-listed/evidence/sub/deeply/nested/file.md",
        ) is False

    def test_sibling_keep_type_policies_are_unaffected(self):
        assert _git_check_ignore(self.repo, "reports/audit/install-defect-sweep-latest/report.json") is False
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/cells/readme.md") is False
        assert _git_check_ignore(self.repo, "reports/audit/st054/sweep-report.json") is True
        assert _git_check_ignore(self.repo, "reports/repo-presenter-regen-full/_scratch/x.md") is True

    def test_unrelated_sibling_report_dir_stays_ignored(self):
        """reports/plan_state_backup/ or reports/other-thing/ must not be
        accidentally swept in by a loose prefix match on 'plan_state'."""
        assert _git_check_ignore(self.repo, "reports/plan_state_backup/x.md") is True
        assert _git_check_ignore(self.repo, "reports/some-other-report/x.md") is True


class TestRealGitCheckIgnoreWholeSubtreeNestedUnderKeepType:
    """The nested-position regression control the taskcard specifically asked
    for: a whole_subtree root nested one level below a keep-type ancestor root
    (reports/audit tracks named child 'y' via 'keep', AND wholesale-tracks the
    further, unbounded 'reports/audit/full-dump' subtree beneath it). Mirrors
    TestRealGitCheckIgnoreNestedPolicyRoot but with the deeper root's TYPE
    swapped from literal to whole_subtree, proving render_merged_tree()
    handles the two types correctly regardless of which is the ancestor and
    which is the descendant."""

    @pytest.fixture(autouse=True)
    def _init_repo(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(
            textwrap.dedent(
                """\
                schema_version: 1
                policies:
                  - root: reports/audit
                    keep:
                      - type: literal
                        names: ["y"]
                  - root: reports/audit/full-dump
                    type: whole_subtree
                """
            ),
            encoding="utf-8",
        )
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("node_modules\nreports/\n*.pyc\n", encoding="utf-8")
        gtp.configure(repo_root=tmp_path, policy_path=policy_path, gitignore_path=gitignore_path)
        assert gtp.main(["--fix"]) == 0
        self.repo = tmp_path
        yield
        gtp.configure(
            repo_root=gtp._DEFAULT_REPO_ROOT,
            policy_path=gtp._DEFAULT_REPO_ROOT / "scripts/pipeline/config/git_tracking_policy.yaml",
            gitignore_path=gtp._DEFAULT_REPO_ROOT / ".gitignore",
        )

    def test_ancestor_roots_own_keep_name_is_not_ignored(self):
        assert _git_check_ignore(self.repo, "reports/audit/y/report.json") is False

    def test_nested_whole_subtree_root_itself_is_tracked(self):
        assert _git_check_ignore(self.repo, "reports/audit/full-dump/report.json") is False

    def test_nested_whole_subtree_roots_unnamed_deep_subdirectory_is_tracked(self):
        """The exact behavior that would break if the old (pre-TC-GOV-01-01)
        engine's nested-root fix were merely reused as-is without a real
        whole_subtree branch: a keep-type nested root only tracks its own
        named children, but a whole_subtree nested root must track EVERYTHING
        below it, including subdirectories with no name registered anywhere."""
        assert _git_check_ignore(
            self.repo, "reports/audit/full-dump/anything/goes/here/file.md"
        ) is False

    def test_untracked_sibling_under_ancestor_root_stays_ignored(self):
        assert _git_check_ignore(self.repo, "reports/audit/st054/sweep-report.json") is True
