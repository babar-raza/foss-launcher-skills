"""extraction/scout.py — Scout orchestration class.

Moved from scout.py (SC-09). Thin orchestrator that delegates all extraction
work to the specialized extraction/ sub-modules.

Backward-compat note: tests use ``import scout; scout.Scout(...)`` — the
top-level scout.py re-exports Scout from here via::

    from extraction.scout import Scout  # noqa: F401
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import subprocess
from pathlib import Path
from typing import Any

from extraction.tree_helpers import (
    PLATFORM_TO_LANG,
    _CLASS_TYPES,
    _FUNC_TYPES,
    _FILE_EXTENSIONS,
    _NOT_IMPL_PATTERNS,
    _collect_source_files,
    _node_name,
    get_parser,
)
from extraction.package_root import detect_package_root
from extraction.package_manifest import parse_manifest
from extraction.formats import detect_formats
from extraction.claims import build_identity_claims
from extraction.snippets import extract_snippets
from extraction.api_surface import extract_api_surface, _JAVA_OBJECT_METHODS
from extraction.outputs import write_outputs

LOG = logging.getLogger("scout")

# Pipeline root (parent of this file's directory)
_PIPELINE_ROOT = Path(__file__).resolve().parents[1]


class Scout:
    """Main extraction engine."""

    # Backward-compat class attribute — tests reference scout.Scout._JAVA_OBJECT_METHODS
    _JAVA_OBJECT_METHODS = _JAVA_OBJECT_METHODS  # noqa: F841

    def __init__(self, family: str, platform: str, repo: Path, output: Path):
        self.family = family
        self.platform = platform
        self.repo = repo
        self.output = output
        self.language = PLATFORM_TO_LANG[platform]
        self.parser = get_parser(self.language)
        self.pkg_root = detect_package_root(repo, platform)
        self.manifest = parse_manifest(repo, platform)
        self.classes: list[dict[str, Any]] = []
        self.claims: list[dict[str, Any]] = []
        self.formats: list[dict[str, Any]] = []
        self.limitations: list[dict[str, Any]] = []
        self.snippets: list[dict[str, Any]] = []
        self.class_graph: list[dict[str, Any]] = []
        self.coverage: list[dict[str, Any]] = []
        self.packages: set[str] = set()
        self.scanned_files: list[str] = []

    # -- claim helpers -----------------------------------------------------

    def _claim_id(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
        return f"CLM-{self.family}-{h}"

    def _add_claim(self, kind: str, text: str, file: str = "", line: int = 0):
        cid = self._claim_id(text)
        evidence = []
        if file:
            evidence.append({"file": file, "line": line})
        self.claims.append({
            "claim_id": cid,
            "kind": kind,
            "text": text,
            "confidence": 1.0,
            "claim_source": "scout",
            "evidence": evidence,
        })

    # -- main pipeline -----------------------------------------------------

    def run(self):
        LOG.info("Extracting %s/%s from %s", self.family, self.platform, self.repo)
        LOG.info("Package root: %s", self.pkg_root)

        self._extract_api_surface()
        self._enrich_docstrings()
        self._detect_formats()
        self._detect_limitations()
        self._extract_snippets()
        self._build_identity_claims()
        self._build_class_graph()
        self._build_coverage()
        self._write_outputs()
        self._log_extraction_quality()

    # -- API surface -------------------------------------------------------

    def _synthesize_java_properties(self, methods, cname: str, rel: str,
                                    properties: list) -> None:
        """Backward-compat Scout method — tests call Scout._synthesize_java_properties directly.

        Logic lives canonically in extraction.api_surface._synthesize_java_properties;
        this wrapper preserves the old mutate-in-place, self._add_claim interface.
        """
        getters: dict = {}
        for m in methods:
            name = m["name"]
            if name in self._JAVA_OBJECT_METHODS:
                continue
            params = m.get("params", [])
            if (name.startswith("get") and len(name) > 3
                    and name[3].isupper() and len(params) == 0):
                getters[name[3].lower() + name[4:]] = m
            elif (name.startswith("is") and len(name) > 2
                  and name[2].isupper() and len(params) == 0):
                getters[name[2].lower() + name[3:]] = m
        for prop_name, getter in getters.items():
            ptype = getter.get("return_type", "")
            properties.append({"name": prop_name, "type": ptype, "line": getter["line"]})
            self._add_claim("api_method",
                            f"{cname}.{prop_name} property of type {ptype}",
                            rel, getter["line"])

    def _extract_api_surface(self):
        """Delegate to extraction.api_surface.extract_api_surface (SC-07)."""
        new_classes, new_claims, new_files, new_pkgs = extract_api_surface(
            self.parser, self.language, self.pkg_root, self.repo, self.family)
        LOG.info("Scanning %d source files", len(new_files))
        self.classes.extend(new_classes)
        self.claims.extend(new_claims)
        self.scanned_files.extend(new_files)
        self.packages.update(new_pkgs)

    # -- Docstring enrichment -----------------------------------------------

    def _enrich_docstrings(self):
        """Post-process extracted classes with platform-specific docstring enrichers.

        Populates empty ``doc`` fields on class/method records using
        Javadoc (Java), Doxygen (C++), or XML doc comments (.NET/C#).
        """
        try:
            spec = importlib.util.spec_from_file_location(
                "scout_enrichers",
                _PIPELINE_ROOT / "scout_enrichers" / "__init__.py",
            )
            if spec is None or spec.loader is None:
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            enrich_classes = mod.enrich_classes
        except Exception:
            return

        count = enrich_classes(self.classes, self.repo, self.platform)
        if count:
            LOG.info("Docstring enrichment: populated %d items", count)

    # -- Format detection --------------------------------------------------

    def _detect_formats(self):
        """Delegate to extraction.formats.detect_formats (SC-04)."""
        new_formats, new_claims = detect_formats(
            self.parser, self.language, self.pkg_root, self.repo, self.family)
        self.formats.extend(new_formats)
        self.claims.extend(new_claims)

    # -- Limitation detection ----------------------------------------------

    def _detect_limitations(self):
        pattern = _NOT_IMPL_PATTERNS.get(self.language)
        if pattern is None:
            return

        ext = _FILE_EXTENSIONS.get(self.language, ".py")
        files = _collect_source_files(self.pkg_root, ext)

        class_types = _CLASS_TYPES.get(self.language, set())
        func_types = _FUNC_TYPES.get(self.language, set())

        for fpath in files:
            rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            if not pattern.search(text):
                continue

            src_bytes = text.encode("utf-8")
            tree = self.parser.parse(src_bytes)
            root = tree.root_node

            for i, line in enumerate(text.splitlines(), 1):
                if not pattern.search(line):
                    continue

                enclosing_class = ""
                enclosing_method = ""

                byte_offset = sum(len(l.encode("utf-8")) + 1
                                  for l in text.splitlines()[:i - 1])
                node = root.descendant_for_byte_range(byte_offset, byte_offset + 1)
                while node:
                    if node.type in func_types:
                        enclosing_method = _node_name(node, self.language)
                    if node.type in class_types:
                        enclosing_class = _node_name(node, self.language)
                    node = node.parent

                self.limitations.append({
                    "file": rel,
                    "line": i,
                    "class": enclosing_class,
                    "method": enclosing_method,
                    "text": line.strip(),
                })
                self._add_claim(
                    "limitation",
                    f"Not implemented: {enclosing_class}.{enclosing_method} in {rel}:{i}",
                    rel, i)

    # -- Snippet extraction ------------------------------------------------

    def _extract_snippets(self):
        """Delegate to extraction.snippets.extract_snippets (SC-06)."""
        self.snippets.extend(extract_snippets(
            self.parser, self.language, self.pkg_root, self.repo,
            self.classes, self.formats))
        LOG.info("Extracted %d function-level snippets", len(self.snippets))

    # -- Identity claims ---------------------------------------------------

    def _build_identity_claims(self):
        """Delegate to extraction.claims.build_identity_claims (SC-05)."""
        self.claims.extend(build_identity_claims(self.manifest, self.family))

    # -- Class graph -------------------------------------------------------

    def _build_class_graph(self):
        name_set = {c["name"] for c in self.classes}
        for cls in self.classes:
            if cls.get("bases"):
                for base in cls["bases"]:
                    self.class_graph.append({
                        "child": cls["name"],
                        "parent": base,
                        "relationship": "inherits",
                        "internal": base in name_set,
                    })

    # -- Coverage matrix ---------------------------------------------------

    # Top-level directories that snippets.py extracts test code from.
    # MUST stay in sync with the "tests" and "test" entries in
    # extraction/snippets.py snippet_dirs (line 144):
    #   snippet_dirs = ["tests", "test", "examples", "example", "samples", "demo"]
    # If a new test-type directory is added there, add it here too.
    _SNIPPET_TEST_DIRS = ("tests/", "test/")

    def _build_coverage(self):
        for cls in self.classes:
            if cls.get("kind") == "function":
                continue
            self.coverage.append({
                "class": cls["name"],
                "file": cls["file"],
                "kind": cls.get("kind", ""),
                "method_count": len(cls.get("methods", [])),
                "property_count": len(cls.get("properties", [])),
                "has_doc": bool(cls.get("doc")),
                "has_tests": any(
                    s.get("source_file", "").startswith(self._SNIPPET_TEST_DIRS)
                    for s in self.snippets
                    if cls["name"] in s.get("classes_used", [])
                ),
                "enum_members": len(cls.get("enum_members", [])),
            })

    # -- Extraction quality gate -------------------------------------------

    def _log_extraction_quality(self):
        """Compute and log extraction quality metrics after all extraction steps.

        Metrics computed:
        - return_type_fill_rate: fraction of methods that have a non-empty
          return_type field.  For C++ this should be >= 0.80 after S-Fix-8;
          a WARNING is printed to stderr if the threshold is not met.
        - property_fill_rate: fraction of non-function class records that have
          at least one property entry.
        - has_tests_fill_rate: fraction of non-function class records that have
          has_tests=True.  A WARNING is printed when the rate is 0% but test
          snippets are present (indicating a likely extraction regression).

        These metrics are intentionally log-only — no model.yaml is written
        here.  A downstream audit step may act on them.
        """
        import sys

        total_methods = 0
        methods_with_return_type = 0
        total_classes = 0
        classes_with_properties = 0
        classes_with_tests = 0

        for cls in self.classes:
            if cls.get("kind") == "function":
                continue
            total_classes += 1
            if cls.get("properties"):
                classes_with_properties += 1
            for m in cls.get("methods", []):
                total_methods += 1
                if m.get("return_type", ""):
                    methods_with_return_type += 1

        for entry in self.coverage:
            if entry.get("has_tests"):
                classes_with_tests += 1

        return_type_fill_rate = (
            methods_with_return_type / total_methods if total_methods > 0 else 0.0
        )
        property_fill_rate = (
            classes_with_properties / total_classes if total_classes > 0 else 0.0
        )
        has_tests_fill_rate = (
            classes_with_tests / total_classes if total_classes > 0 else 0.0
        )

        LOG.info(
            "Extraction quality: return_type_fill=%.2f property_fill=%.2f"
            " has_tests_fill=%.2f",
            return_type_fill_rate,
            property_fill_rate,
            has_tests_fill_rate,
        )

        if self.language == "cpp" and total_methods > 0 and return_type_fill_rate < 0.80:
            print(
                f"WARNING: C++ return_type_fill_rate={return_type_fill_rate:.2f} "
                f"< 0.80 threshold ({methods_with_return_type}/{total_methods} methods "
                f"have return types). Check extraction/api_surface.py.",
                file=sys.stderr,
            )

        # Warn when has_tests is 0% but test snippets exist — indicates a
        # regression in _build_coverage or snippets extraction.
        test_snippet_count = sum(
            1 for s in self.snippets
            if s.get("source_file", "").startswith(self._SNIPPET_TEST_DIRS)
        )
        if classes_with_tests == 0 and test_snippet_count > 0 and total_classes > 0:
            print(
                f"WARNING: has_tests_fill_rate=0.00 but {test_snippet_count} test "
                f"snippet(s) exist. Check extraction/scout.py _build_coverage "
                f"and _SNIPPET_TEST_DIRS.",
                file=sys.stderr,
            )

    # -- Output ------------------------------------------------------------

    def _get_repo_sha(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo), capture_output=True, text=True, timeout=10)
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_repo_url(self) -> str:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(self.repo), capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _write_outputs(self):
        """Delegate to extraction.outputs.write_outputs (SC-08)."""
        write_outputs(
            output=self.output,
            family=self.family,
            platform=self.platform,
            manifest=self.manifest,
            classes=self.classes,
            claims=self.claims,
            formats=self.formats,
            limitations=self.limitations,
            snippets=self.snippets,
            class_graph=self.class_graph,
            coverage=self.coverage,
            scanned_files=self.scanned_files,
            packages=self.packages,
            language=self.language,
            repo_sha=self._get_repo_sha(),
            repo_url=self._get_repo_url(),
            package_root=str(self.pkg_root.relative_to(self.repo)).replace("\\", "/"),
        )
