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
