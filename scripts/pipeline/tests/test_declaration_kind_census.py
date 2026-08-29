"""Declaration-kind census (TC-MT040-40, D-1).

Generic version of the check that would have caught TC-10's original gap
(tree_helpers._CLASS_TYPES["typescript"] silently lacking
abstract_class_declaration) BEFORE a human found it by hand: parse each
platform's real source with the real tree-sitter grammar, collect the set of
declaration-shaped node kinds actually observed, and assert that set is a
subset of (class_kinds ∪ func_kinds ∪ module_kinds ∪ declared_ignored_kinds)
as declared in config/platform_capabilities.yaml. Anything observed outside
all four is a real, previously-invisible gap -- the census fails loud instead
of a human having to notice a missing node type in a live parse probe.

Two source families:
  1. Fixture packages under tests/fixtures/ -- one per platform (python_pkg,
     net_pkg, java_pkg, cpp_pkg, go_pkg, rust_crate, ts_flat_package). MUST
     pass for every platform (part of this file's green bar).
  2. The real clone-cache root of one already-registered product per
     platform, when present under runs/.clone_cache/ in THIS worktree --
     guarded by .is_dir(), skipped (never failed) when absent. This worktree
     is isolated from the main repo's clone cache, so these are expected to
     skip here; documented, not silently omitted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extraction.tree_helpers import get_parser  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "platform_capabilities.yaml"
FIXTURES = Path(__file__).parent / "fixtures"

# Repo root: scripts/pipeline/tests/test_declaration_kind_census.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
CLONE_CACHE = REPO_ROOT / "runs" / ".clone_cache"


def _load_caps() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


CAPS = _load_caps()
PLATFORMS = sorted(CAPS["platforms"].keys())

# ---------------------------------------------------------------------------
# The declaration-shape heuristic: empirically validated (not guessed) by
# running the real tree-sitter grammars over every fixture package under
# tests/fixtures/ and inspecting the actual node kinds produced (see the
# per-platform `declared_ignored_kinds` entries in platform_capabilities.yaml
# for the observed-but-not-a-class/func/module-kind results this classifies
# every one of). Every kind name currently handled anywhere in
# tree_helpers._CLASS_TYPES/_FUNC_TYPES/_MODULE_TYPES across all 7 languages
# ends in one of these suffixes or is the bare word "module" -- verified by
# inspection, not assumed.
_DECL_SUFFIXES = (
    "_declaration", "_definition", "_item", "_specifier", "_spec",
    "_signature", "_module", "_clause",
)
_DECL_EXACT = {"module"}


def _looks_declarationish(kind: str) -> bool:
    return kind in _DECL_EXACT or kind.endswith(_DECL_SUFFIXES)


def _walk_declaration_kinds(node, observed: set, depth: int, max_depth: int) -> None:
    if depth > max_depth:
        return
    for child in node.children:
        if child.is_named and _looks_declarationish(child.type):
            observed.add(child.type)
        _walk_declaration_kinds(child, observed, depth + 1, max_depth)


def collect_declaration_kinds(language: str, source_files: list) -> set:
    """Parse every file in *source_files* with the real tree-sitter grammar
    for *language* and return the set of declaration-shaped node kinds
    observed anywhere in the first 6 levels of each file's parse tree (deep
    enough to reach declarations nested one wrapper inside an
    export_statement/namespace/impl block, per the empirical probe that
    built this file's suffix list)."""
    parser = get_parser(language)
    observed: set = set()
    for f in source_files:
        try:
            src = f.read_bytes()
        except OSError:
            continue
        tree = parser.parse(src)
        _walk_declaration_kinds(tree.root_node, observed, 0, 6)
    return observed


def allowed_kinds_for(platform: str) -> set:
    """(class_kinds ∪ func_kinds ∪ module_kinds ∪ declared_ignored_kinds) for
    *platform*, read from the real platform_capabilities.yaml declaration --
    this is the actual subset test's right-hand side."""
    row = CAPS["platforms"][platform]
    allowed = set(row["class_kinds"]) | set(row["func_kinds"]) | set(row["module_kinds"])
    allowed |= set(row["declared_ignored_kinds"].keys())
    return allowed


def assert_census_subset(platform: str, observed: set, allowed: set) -> None:
    """The actual subset check, factored out so the negative-control test
    below can call the EXACT same comparison against a mutated `allowed` set
    rather than duplicating the assertion logic."""
    gap = observed - allowed
    assert not gap, (
        f"{platform}: real source produced declaration-shaped kind(s) "
        f"{sorted(gap)} that are in NEITHER class_kinds ∪ func_kinds ∪ "
        f"module_kinds NOR declared_ignored_kinds for this platform in "
        f"platform_capabilities.yaml -- this is exactly the class of gap "
        f"TC-10 fixed by hand for TypeScript's abstract_class_declaration; "
        f"either the platform truly needs a new mapped kind (fix the real "
        f"code + re-declare the YAML) or it's genuinely irrelevant noise "
        f"(add it to declared_ignored_kinds with a reason)."
    )


# ---------------------------------------------------------------------------
# Fixture packages: one real source tree per platform.
# ---------------------------------------------------------------------------

_FIXTURE_PACKAGES = {
    "python": (FIXTURES / "python_pkg", ["*.py"]),
    "net": (FIXTURES / "net_pkg", ["*.cs"]),
    "java": (FIXTURES / "java_pkg", ["*.java"]),
    "cpp": (FIXTURES / "cpp_pkg", ["*.h", "*.cpp"]),
    "go": (FIXTURES / "go_pkg", ["*.go"]),
    "rust": (FIXTURES / "rust_crate", ["*.rs"]),
    "typescript": (FIXTURES / "ts_flat_package", ["*.ts"]),
}


def _collect_files(root: Path, patterns: list) -> list:
    files: list = []
    for pat in patterns:
        files.extend(sorted(root.rglob(pat)))
    return files


class TestFixturePackageCensus:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_fixture_package_kinds_are_all_allowed(self, platform):
        root, patterns = _FIXTURE_PACKAGES[platform]
        assert root.is_dir(), f"{platform}: expected fixture package at {root} is missing"
        files = _collect_files(root, patterns)
        assert files, f"{platform}: fixture package at {root} has no {patterns} source files"

        lang = CAPS["platforms"][platform]["language"]
        observed = collect_declaration_kinds(lang, files)
        allowed = allowed_kinds_for(platform)
        assert_census_subset(platform, observed, allowed)

    def test_typescript_fixture_observes_abstract_class_declaration(self):
        """Explicit acceptance check from the card description: the census
        must show abstract_class_declaration as HANDLED for typescript, not
        merely absent from the observed set because the fixture never
        contained one. ts_flat_package/src/shapes.ts was added by this card
        specifically to cover this (it didn't exist before -- checked
        first, per the card's own instruction)."""
        root, patterns = _FIXTURE_PACKAGES["typescript"]
        files = _collect_files(root, patterns)
        observed = collect_declaration_kinds("typescript", files)
        assert "abstract_class_declaration" in observed
        assert "abstract_class_declaration" in CAPS["platforms"]["typescript"]["class_kinds"]

    def test_typescript_fixture_covers_every_declared_class_and_module_kind(self):
        """Stronger acceptance proof than the single-kind check above: every
        kind typescript's YAML row claims to handle in class_kinds/
        module_kinds is actually exercised somewhere in the fixture (so the
        census is a real proof, not a vacuous subset check against an
        under-populated fixture)."""
        root, patterns = _FIXTURE_PACKAGES["typescript"]
        files = _collect_files(root, patterns)
        observed = collect_declaration_kinds("typescript", files)
        row = CAPS["platforms"]["typescript"]
        for kind in row["class_kinds"] + row["module_kinds"]:
            assert kind in observed, (
                f"typescript: declared kind {kind!r} is never actually "
                f"observed in ts_flat_package -- the fixture doesn't "
                f"exercise this capability, so a regression in it would "
                f"go undetected by this census"
            )


# ---------------------------------------------------------------------------
# Real clone-cache root, one already-registered product per platform, when
# present. This worktree is isolated from the main repo's clone cache
# (verified: runs/.clone_cache/ does not exist here at all) -- every one of
# these is expected to skip in THIS worktree, and that is the correct,
# honest behavior per the card's own instruction ("skip gracefully, don't
# fail, if a given product's clone isn't present").
# ---------------------------------------------------------------------------

# family/platform pairs chosen from data/products.json's real active rows
# (one already-registered product per platform).
_CLONE_TARGETS = {
    "python": ("aspose_pdf_python", ["*.py"]),
    "net": ("aspose_pdf_net", ["*.cs"]),
    "java": ("aspose_pdf_java", ["*.java"]),
    "cpp": ("aspose_pdf_cpp", ["*.h", "*.cpp", "*.cc", "*.hpp"]),
    "go": ("aspose_pdf_go", ["*.go"]),
    "rust": ("aspose_cells_rust", ["*.rs"]),
    "typescript": ("aspose_3d_typescript", ["*.ts"]),
}


class TestRealCloneCacheCensus:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_real_clone_kinds_are_all_allowed_when_present(self, platform):
        clone_dir_name, patterns = _CLONE_TARGETS[platform]
        clone_root = CLONE_CACHE / clone_dir_name
        if not clone_root.is_dir():
            pytest.skip(
                f"{platform}: {clone_root} not present in this worktree's "
                f"clone cache -- isolated worktree, expected; census relies "
                f"on the fixture-package census (TestFixturePackageCensus) "
                f"instead, which must still pass."
            )
        lang = CAPS["platforms"][platform]["language"]
        files = _collect_files(clone_root, patterns)
        if not files:
            pytest.skip(f"{platform}: {clone_root} present but no {patterns} files found")
        observed = collect_declaration_kinds(lang, files)
        allowed = allowed_kinds_for(platform)
        assert_census_subset(platform, observed, allowed)


# ---------------------------------------------------------------------------
# Negative control: prove the census fails closed, not just once and never
# exercised again.
# ---------------------------------------------------------------------------


class TestNegativeControlCensusCatchesDrift:
    def test_census_fails_closed_when_typescript_class_kinds_regresses(self):
        """Simulates the exact TC-10 regression by re-running the SAME
        assert_census_subset() helper the real census test above calls,
        against a LOCAL COPY of the allowed-kinds set with
        abstract_class_declaration removed (never mutates the real YAML
        file or a live module -- a local copy is what fits this repo's
        conventions, per check_monkeypatch_lint.py's T2 ban on internal
        monkeypatching)."""
        root, patterns = _FIXTURE_PACKAGES["typescript"]
        files = _collect_files(root, patterns)
        observed = collect_declaration_kinds("typescript", files)
        assert "abstract_class_declaration" in observed  # precondition for a meaningful negative control

        regressed_allowed = allowed_kinds_for("typescript") - {"abstract_class_declaration"}
        with pytest.raises(AssertionError):
            assert_census_subset("typescript", observed, regressed_allowed)

        # Sanity: the real, unmutated allowed set still passes.
        assert_census_subset("typescript", observed, allowed_kinds_for("typescript"))

    def test_census_fails_closed_when_a_declared_ignored_kind_is_removed(self):
        """The other regression direction: shrinking declared_ignored_kinds
        (not just class/func/module_kinds) must also make previously-inert
        noise kinds start failing the census -- proving declared_ignored_kinds
        is load-bearing, not decorative."""
        root, patterns = _FIXTURE_PACKAGES["rust"]
        files = _collect_files(root, patterns)
        observed = collect_declaration_kinds("rust", files)
        assert "use_declaration" in observed  # rust_crate genuinely has imports

        regressed_allowed = allowed_kinds_for("rust") - {"use_declaration"}
        with pytest.raises(AssertionError):
            assert_census_subset("rust", observed, regressed_allowed)

        assert_census_subset("rust", observed, allowed_kinds_for("rust"))
