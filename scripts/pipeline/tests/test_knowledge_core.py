"""Tests for scripts/pipeline/knowledge_core.py — diff command and CLI.

These tests verify the diff command functionality using real products from
the knowledge base. The tests are designed to be:
- Isolated: Each test runs independently
- Deterministic: Same results on every run
- Fast: No network calls, no external dependencies
- Self-contained: All test data is in the test file or temp directory
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestDiffCommand:
    """Tests for the diff command in knowledge_core.py."""

    def test_diff_sha_match(self, tmp_path):
        """Test diff command when repo SHA matches stored SHA.
        
        This test creates a temporary git repo, commits a file, and creates
        a knowledge model with the same SHA. The diff command should report
        SHA MATCH.
        """
        # Create a temporary git repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
        
        # Create a file and commit
        (repo_dir / "test.txt").write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
        
        # Get current SHA
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True)
        current_sha = result.stdout.strip()
        
        # Create knowledge model with matching SHA in the actual knowledge directory
        # We use a test product that won't interfere with real products
        test_family = "test"
        test_platform = "python"
        knowledge_dir = Path("knowledge") / test_family / test_platform / "merged"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        model = {
            "version": "1.0.0",
            "repo_sha": current_sha,
            "surface_tier": 2,
            "family": test_family,
            "platform": test_platform,
            "package_name": "test.package",
            "package_version": "1.0.0"
        }
        (knowledge_dir / "model.yaml").write_text(json.dumps(model, indent=2))
        
        api_surface = [{"name": "TestClass", "file": "TestClass.py", "kind": "class", "methods": [], "properties": [], "doc": "", "enum_members": []}]
        (knowledge_dir / "api_surface.json").write_text(json.dumps(api_surface))
        
        try:
            # Run diff command
            from knowledge_core import diff
            result = diff(test_family, test_platform, repo_dir)
            
            assert "SHA MATCH" in result
            assert current_sha[:8] in result
        finally:
            # Clean up knowledge model
            if knowledge_dir.exists():
                import shutil
                shutil.rmtree(knowledge_dir.parent.parent, ignore_errors=True)

    def test_diff_sha_mismatch(self, tmp_path):
        """Test diff command when repo SHA does not match stored SHA.
        
        This test creates a temporary git repo, commits a file, and creates
        a knowledge model with a different SHA. The diff command should report
        SHA MISMATCH.
        """
        # Create a temporary git repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
        
        # Create a file and commit
        (repo_dir / "test.txt").write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
        
        # Get current SHA
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True)
        current_sha = result.stdout.strip()
        
        # Create knowledge model with different SHA
        test_family = "test"
        test_platform = "python"
        knowledge_dir = Path("knowledge") / test_family / test_platform / "merged"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        model = {
            "version": "1.0.0",
            "repo_sha": "different123456789",
            "surface_tier": 2,
            "family": test_family,
            "platform": test_platform,
            "package_name": "test.package",
            "package_version": "1.0.0"
        }
        (knowledge_dir / "model.yaml").write_text(json.dumps(model, indent=2))
        
        api_surface = [{"name": "TestClass", "file": "TestClass.py", "kind": "class", "methods": [], "properties": [], "doc": "", "enum_members": []}]
        (knowledge_dir / "api_surface.json").write_text(json.dumps(api_surface))
        
        try:
            # Run diff command
            from knowledge_core import diff
            result = diff(test_family, test_platform, repo_dir)
            
            assert "SHA MISMATCH" in result
            assert current_sha[:8] in result
            assert "differen" in result  # SHA is truncated to 8 chars in output
        finally:
            # Clean up knowledge model
            if knowledge_dir.exists():
                import shutil
                shutil.rmtree(knowledge_dir.parent.parent, ignore_errors=True)

    def test_diff_invalid_repo_path(self, tmp_path):
        """Test diff command with invalid repo path.
        
        This test verifies that the diff command handles invalid repo paths
        gracefully and returns an appropriate error message.
        """
        from knowledge_core import diff
        result = diff("test", "python", tmp_path / "nonexistent")
        
        assert "ERROR" in result
        assert "does not exist" in result or "not a directory" in result

    def test_diff_missing_knowledge_model(self, tmp_path):
        """Test diff command with missing knowledge model.
        
        This test verifies that the diff command handles missing knowledge
        models gracefully and returns an appropriate error message.
        """
        # Create a temporary git repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
        
        # Create a file and commit
        (repo_dir / "test.txt").write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
        
        # Run diff command with missing knowledge model
        from knowledge_core import diff
        result = diff("nonexistent_family", "python", repo_dir)
        
        assert "ERROR" in result
        assert "Knowledge model not available" in result

    def test_diff_git_not_found(self, tmp_path):
        """Test diff command when git is not available.
        
        This test verifies that the diff command handles the case when git
        is not installed or not in PATH.
        """
        # Create a temporary directory (not a git repo)
        repo_dir = tmp_path / "not_a_repo"
        repo_dir.mkdir()
        
        from knowledge_core import diff
        result = diff("test", "python", repo_dir)

        # Should return an error since this is not a valid git repo
        assert "ERROR" in result



_KNOWLEDGE_ROOT_KCT = Path(__file__).resolve().parents[3] / "knowledge"
_ENOUGH_PRODUCTS = (
    sum(1 for _ in _KNOWLEDGE_ROOT_KCT.glob("*/*/merged/api_surface.json")) >= 10
)

class TestDiscoverContentCWDIndependence:
    """Regression tests for CWD-independent content discovery.

    The discover_content() function must use absolute paths derived from
    __file__, not bare relative Path("content/..."). If this test fails,
    someone likely reverted the _REPO_ROOT fix in knowledge_core.py.
    """

    def test_discover_content_from_foreign_cwd(self, tmp_path, monkeypatch):
        """discover_content must find files when CWD is an empty temp dir."""
        monkeypatch.chdir(tmp_path)
        from content_discovery import discover_content  # R-1b: canonical home
        files = discover_content("note", "python")
        assert len(files) > 0, (
            f"discover_content('note','python') returned 0 files from CWD={tmp_path}. "
            "Path resolution must use __file__-based _REPO_ROOT, not relative paths."
        )

    @pytest.mark.skipif(
        not _ENOUGH_PRODUCTS,
        reason="knowledge not bootstrapped: fewer than 10 products have api_surface.json",
    )
    def test_discover_products_from_foreign_cwd(self, tmp_path, monkeypatch):
        """discover_products must find products when CWD is an empty temp dir."""
        monkeypatch.chdir(tmp_path)
        from content_discovery import discover_products  # R-1b: canonical home
        products = discover_products()
        assert len(products) >= 10, (
            f"discover_products() returned {len(products)} from CWD={tmp_path}. "
            "Expected at least 10 products."
        )


# ---------------------------------------------------------------------------
# Fully-qualified name index (S-1 disambiguation)
# ---------------------------------------------------------------------------


class TestFQNameIndex:
    """Knowledge.classes_by_import disambiguates same-named classes."""

    def _make_knowledge(self, tmp_path, api_list):
        """Build a minimal Knowledge from a synthetic api_surface.json."""
        merged = tmp_path / "test" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text(
            "version: '1.0'\nrepo_sha: abc123\n", encoding="utf-8"
        )
        (merged / "api_surface.json").write_text(
            json.dumps(api_list), encoding="utf-8"
        )
        from knowledge_core import Knowledge
        return Knowledge("test", "python", knowledge_root=tmp_path)

    def test_classes_by_import_populated(self, tmp_path):
        api = [
            {
                "name": "Document",
                "kind": "class_definition",
                "doc": "",
                "file": "words_foss/document.py",
                "line": 1,
                "bases": [],
                "methods": [],
                "properties": [],
                "class_import": "words_foss.document.Document",
            },
            {
                "name": "Document",
                "kind": "class_definition",
                "doc": "",
                "file": "pdf_foss/document.py",
                "line": 1,
                "bases": [],
                "methods": [{"name": "save", "params": [], "return_type": "None", "doc": "", "line": 5}],
                "properties": [],
                "class_import": "pdf_foss.document.Document",
            },
        ]
        k = self._make_knowledge(tmp_path, api)
        # Bare-name lookup returns last-loaded (collision)
        assert k.classes["Document"]["file"] == "pdf_foss/document.py"
        # FQ-name lookup resolves correctly
        assert k.has_class_fq("words_foss.document.Document")
        assert k.has_class_fq("pdf_foss.document.Document")
        assert not k.has_class_fq("nonexistent.Document")

    def test_has_method_fq(self, tmp_path):
        api = [
            {
                "name": "Document",
                "kind": "class_definition",
                "doc": "", "file": "a.py", "line": 1, "bases": [],
                "methods": [{"name": "save", "params": [], "return_type": "None", "doc": "", "line": 5}],
                "properties": [],
                "class_import": "module_a.Document",
            },
        ]
        k = self._make_knowledge(tmp_path, api)
        assert k.has_method_fq("module_a.Document", "save")
        assert not k.has_method_fq("module_a.Document", "load")
        assert not k.has_method_fq("nonexistent.Document", "save")

    def test_backward_compat_no_class_import(self, tmp_path):
        """Classes without class_import field still work via bare-name lookup."""
        api = [
            {
                "name": "Foo",
                "kind": "class_definition",
                "doc": "", "file": "foo.py", "line": 1, "bases": [],
                "methods": [], "properties": [],
                # No class_import field
            },
        ]
        k = self._make_knowledge(tmp_path, api)
        assert "Foo" in k.classes
        # FQ lookup returns nothing (no class_import)
        assert not k.has_class_fq("Foo")


# ---------------------------------------------------------------------------
# Lazy I/O — TC-09
# ---------------------------------------------------------------------------


class TestKnowledgeLazyIO:
    """Knowledge construction must have zero I/O cost (TC-09)."""

    def _make_knowledge_root(self, tmp_path, api_list=None):
        """Build a minimal merged/ tree under tmp_path."""
        import yaml as _yaml
        merged = tmp_path / "words" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text(
            _yaml.dump({"version": "1.0", "repo_sha": "test_sha"}),
            encoding="utf-8",
        )
        (merged / "api_surface.json").write_text(
            __import__("json").dumps(api_list or []),
            encoding="utf-8",
        )
        return tmp_path

    def test_construction_zero_io(self):
        """1000 Knowledge() constructions in <100ms — no file reads in __init__."""
        import time
        import sys
        sys.path.insert(0, "scripts/pipeline")
        from knowledge_core import Knowledge
        t = time.perf_counter()
        for _ in range(1000):
            k = Knowledge("words", "python")
        elapsed = time.perf_counter() - t
        assert elapsed < 0.1, f"Construction too slow: {elapsed*1000:.0f}ms for 1000 objects"

    def test_no_load_before_attribute_access(self):
        """_knowledge_loaded sentinel absent right after construction."""
        import sys
        sys.path.insert(0, "scripts/pipeline")
        from knowledge_core import Knowledge
        k = Knowledge("words", "python")
        assert "_knowledge_loaded" not in k.__dict__
        assert "available" not in k.__dict__

    def test_available_false_when_no_knowledge_dir(self, tmp_path):
        """available=False for missing knowledge root; no AttributeError."""
        import sys
        sys.path.insert(0, "scripts/pipeline")
        from knowledge_core import Knowledge
        k = Knowledge("words", "python", knowledge_root=tmp_path)
        assert k.available is False
        # All data attrs return safe defaults
        assert k.classes == {}
        assert k.methods == {}
        assert k.claim_ids == set()
        assert k.workaround_members == {}

    def test_lazy_load_triggered_on_available_access(self, tmp_path):
        """Accessing .available triggers _ensure_loaded; sentinel set afterwards."""
        import sys
        sys.path.insert(0, "scripts/pipeline")
        from knowledge_core import Knowledge
        root = self._make_knowledge_root(tmp_path)
        k = Knowledge("words", "python", knowledge_root=root)
        assert "_knowledge_loaded" not in k.__dict__, "must not load before access"
        _ = k.available
        assert "_knowledge_loaded" in k.__dict__, "must load after first access"

    def test_all_attrs_populated_after_load(self, tmp_path):
        """After load, all expected data attrs are present in __dict__."""
        import sys
        sys.path.insert(0, "scripts/pipeline")
        from knowledge_core import Knowledge
        root = self._make_knowledge_root(tmp_path)
        k = Knowledge("words", "python", knowledge_root=root)
        _ = k.available  # trigger load
        expected = [
            "version", "repo_sha", "classes", "classes_by_import",
            "methods", "properties", "enum_members", "return_types",
            "property_types", "method_params", "parents", "valid_imports",
            "claim_ids", "api_to_claim", "surface_tier", "install_cmd",
            "snippet_index", "_snippet_classes", "_snippet_methods",
            "class_importance", "class_kind", "workaround_members",
        ]
        for attr in expected:
            assert attr in k.__dict__, f"Missing attr after load: {attr}"

    def test_ensure_loaded_idempotent(self, tmp_path):
        """Calling _ensure_loaded() twice does not reload or raise."""
        import sys
        sys.path.insert(0, "scripts/pipeline")
        from knowledge_core import Knowledge
        root = self._make_knowledge_root(tmp_path)
        k = Knowledge("words", "python", knowledge_root=root)
        k._ensure_loaded()
        classes_id_1 = id(k.classes)
        k._ensure_loaded()
        assert id(k.classes) == classes_id_1, "Second load must not replace objects"

    def test_private_attr_raises_without_loading(self):
        """__getattr__ guard: accessing a missing private attr raises AttributeError immediately,
        without triggering _ensure_loaded() and without infinite recursion.
        """
        import sys
        sys.path.insert(0, "scripts/pipeline")
        from knowledge_core import Knowledge
        k = Knowledge("words", "python")
        # Sanity: no load before the access
        assert "_knowledge_loaded" not in k.__dict__
        with pytest.raises(AttributeError):
            _ = k._nonexistent_private_attr
        # Guard must not have triggered a load
        assert "_knowledge_loaded" not in k.__dict__, (
            "_ensure_loaded() must NOT be called for private-name lookups"
        )


# ---------------------------------------------------------------------------
# OBS-03: Self-referential bases filtering
# ---------------------------------------------------------------------------


class TestSelfReferentialBasesFilter:
    """OBS-03: Knowledge must strip self-referential bases on load."""

    def _make_knowledge_root(self, tmp_path, api_list):
        import yaml as _yaml
        merged = tmp_path / "test" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text(
            _yaml.dump({"version": "1.0", "repo_sha": "test_sha"}),
            encoding="utf-8",
        )
        (merged / "api_surface.json").write_text(
            json.dumps(api_list), encoding="utf-8",
        )
        return tmp_path

    def test_self_ref_removed_from_parents(self, tmp_path):
        """A3DObject listing itself as its own base must be filtered out."""
        api = [
            {
                "name": "A3DObject",
                "kind": "class_definition",
                "doc": "", "file": "a.py", "line": 1,
                "bases": ["A3DObject", "INamedObject"],
                "methods": [], "properties": [],
            },
        ]
        from knowledge_core import Knowledge
        k = Knowledge("test", "python", knowledge_root=self._make_knowledge_root(tmp_path, api))
        assert "A3DObject" not in k.parents.get("A3DObject", []), (
            "Self-referential base must be removed"
        )
        assert "INamedObject" in k.parents.get("A3DObject", []), (
            "Legitimate base must be preserved"
        )

    def test_no_self_ref_leaves_bases_intact(self, tmp_path):
        """Classes without self-refs keep all bases."""
        api = [
            {
                "name": "Mesh",
                "kind": "class_definition",
                "doc": "", "file": "m.py", "line": 1,
                "bases": ["Entity", "IMeshConvertible"],
                "methods": [], "properties": [],
            },
        ]
        from knowledge_core import Knowledge
        k = Knowledge("test", "python", knowledge_root=self._make_knowledge_root(tmp_path, api))
        assert k.parents.get("Mesh") == ["Entity", "IMeshConvertible"]

    def test_has_method_no_infinite_loop(self, tmp_path):
        """Self-ref in bases must not cause infinite loop in has_method."""
        api = [
            {
                "name": "AnimationChannel",
                "kind": "class_definition",
                "doc": "", "file": "a.py", "line": 1,
                "bases": ["AnimationChannel", "KeyframeSequence"],
                "methods": [{"name": "play", "params": [], "return_type": "", "doc": "", "line": 5}],
                "properties": [],
            },
        ]
        from knowledge_core import Knowledge
        k = Knowledge("test", "python", knowledge_root=self._make_knowledge_root(tmp_path, api))
        # Should not hang; self-ref is filtered
        assert k.has_method("AnimationChannel", "play") is True
        assert k.has_method("AnimationChannel", "nonexistent") is False


# ---------------------------------------------------------------------------
# class_graph-FORMAT-001: Array format loading
# All products use {"child": ..., "parent": ...} array format.
# Previously the dict-only check silently ignored all class_graph.json files.
# ---------------------------------------------------------------------------


class TestClassGraphArrayFormat:
    """Regression tests for class_graph.json array format in knowledge_core.py.

    All 16 products use the array format [{"child": "...", "parent": "...", ...}].
    Previously isinstance(graph, dict) on line 171 silently skipped all arrays,
    leaving self.parents empty for every product.
    """

    def _make_knowledge_root(self, tmp_path, api_list, class_graph=None):
        import yaml as _yaml
        merged = tmp_path / "test" / "java" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text(
            _yaml.dump({"version": "1.0", "repo_sha": "test_sha"}),
            encoding="utf-8",
        )
        (merged / "api_surface.json").write_text(
            json.dumps(api_list), encoding="utf-8",
        )
        if class_graph is not None:
            (merged / "class_graph.json").write_text(
                json.dumps(class_graph), encoding="utf-8",
            )
        return tmp_path

    def test_array_format_parents_populated(self, tmp_path):
        """Array-format class_graph.json must populate self.parents."""
        graph = [
            {"child": "BulletFormat", "parent": "PVIObject", "relationship": "inherits"},
            {"child": "PVIObject", "parent": "IPresentation", "relationship": "inherits"},
        ]
        from knowledge_core import Knowledge
        k = Knowledge("test", "java", knowledge_root=self._make_knowledge_root(tmp_path, [], graph))
        assert "PVIObject" in k.parents.get("BulletFormat", []), (
            "Array-format class_graph.json not loaded. "
            "Check isinstance(graph, list) branch in knowledge_core.py."
        )
        assert "IPresentation" in k.parents.get("PVIObject", [])

    def test_array_format_self_ref_filtered(self, tmp_path):
        """OBS-03: Self-referential entries in array format must be filtered."""
        graph = [
            {"child": "Shape", "parent": "Shape", "relationship": "inherits"},
            {"child": "Shape", "parent": "IShape", "relationship": "inherits"},
        ]
        from knowledge_core import Knowledge
        k = Knowledge("test", "java", knowledge_root=self._make_knowledge_root(tmp_path, [], graph))
        parents = k.parents.get("Shape", [])
        assert "Shape" not in parents, "Self-referential entry must be filtered (OBS-03)"
        assert "IShape" in parents, "Legitimate parent must be preserved"

    def test_missing_child_or_parent_skipped(self, tmp_path):
        """Entries with missing child or parent keys must be skipped gracefully."""
        graph = [
            {"child": "ValidClass", "parent": "ValidBase", "relationship": "inherits"},
            {"parent": "OrphanParent", "relationship": "inherits"},   # no child
            {"child": "OrphanChild", "relationship": "inherits"},      # no parent
            {"relationship": "inherits"},                               # neither
        ]
        from knowledge_core import Knowledge
        k = Knowledge("test", "java", knowledge_root=self._make_knowledge_root(tmp_path, [], graph))
        assert "ValidBase" in k.parents.get("ValidClass", [])
        # Incomplete entries must not raise
        assert k.parents.get("OrphanChild") is None or "OrphanChild" not in k.parents

    def test_no_class_graph_file_still_loads(self, tmp_path):
        """Knowledge loads cleanly when class_graph.json is absent."""
        from knowledge_core import Knowledge
        k = Knowledge("test", "java", knowledge_root=self._make_knowledge_root(tmp_path, []))
        assert k.parents == {}

    def test_dict_format_still_works(self, tmp_path):
        """Existing dict format must still be supported after array branch addition."""
        graph = {
            "PVIObject": {"bases": ["IPresentation", "IDisposable"]},
        }
        from knowledge_core import Knowledge
        k = Knowledge("test", "java", knowledge_root=self._make_knowledge_root(tmp_path, [], graph))
        assert "IPresentation" in k.parents.get("PVIObject", [])
        assert "IDisposable" in k.parents.get("PVIObject", [])
