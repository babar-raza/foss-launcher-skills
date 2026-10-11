"""B16 (MT074): lib/propagation_analyzer.py + commands/diagnostics/propagation_analyze.py.

Offline: real `git init` repos in three shapes, shallow-cloned (depth 2) so baseline deepening is
exercised for real through the injected `ensure_reachable` seam; GT-2 uses the real generic adapter,
GT-1 uses a small test adapter that reads real git objects. Content trees are synthetic.

Shapes (hard gate G-1 -- nothing in the shipped code names any of them):
  JAVA-like    dotted packages, an enum that gains a constant, new options-style classes (GT-1 adapter)
  PYTHON-like  src/<pkg>/<module>.py files (real GT-2 adapter, file hints, lowercase + underscore stems)
  C#-like      PascalCase namespace tree, `src/<Ns>/<Type>.cs` (real GT-2 adapter)
Bundles: java-ish (class_package), C#-ish (namespace) and python-ish (file qualifier) api_surface
fixtures, plus ONE real tracked product bundle against a synthetic mutated copy.
"""
from __future__ import annotations

import copy
import io
import itertools
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import capability_delta as cd
import language_adapters as la
import propagation_analyze as cli
import propagation_analyzer as pa
from core import clone_cache as cc

REPO_ROOT = Path(__file__).resolve().parents[3]
CRIT = pa.load_criteria()


# ── git helpers ──────────────────────────────────────────────────────────────────────────────────

def git(repo, *args):
    r = subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr}"
    return r.stdout.strip()


def build_origin(root: Path, name: str, commits: "list[dict[str, str | None]]"):
    repo = root / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    shas = []
    for i, files in enumerate(commits):
        for rel, text in files.items():
            p = repo / rel
            if text is None:
                p.unlink()
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"c{i}")
        shas.append(git(repo, "rev-parse", "HEAD"))
    return repo, shas


def shallow_clone(origin: Path, dest: Path, depth: int = 2) -> Path:
    r = subprocess.run(["git", "clone", "-q", f"--depth={depth}", origin.as_uri(), str(dest)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return dest


def is_ancestor(repo, sha):
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, "HEAD"],
                          capture_output=True).returncode == 0


@pytest.fixture(autouse=True)
def _isolated_clone_cache_state():
    """core.clone_cache keeps a per-process verdict memo and a 12-fetch cap: without this reset the
    deepening done by earlier tests exhausts the cap and later tests see UNKNOWN. configure() restores
    every knob to its default AND clears the memo / counter."""
    cc.configure()
    yield
    cc.configure()


class Reach:
    """Records every reachability request and delegates to the REAL core.clone_cache tri-state probe."""

    def __init__(self):
        self.calls = []

    def __call__(self, repo, sha):
        self.calls.append(sha)
        return cc.probe_baseline_reachability_at(repo, sha)


def write_model(kroot: Path, family, platform, sha, version="1.0.0"):
    d = kroot / family / platform / "merged"
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.yaml").write_text(f"name: x\nversion: {version}\nrepo_sha: {sha}\nother: 1\n", encoding="utf-8")


# ── origin shapes ────────────────────────────────────────────────────────────────────────────────

JAVA_DOC = "package org.acme.core;\npublic class Document {\n  public void save() {}\n}\n"
JAVA_MODE0 = "package org.acme.core;\npublic enum OutputMode {\n  FLAT, STACKED\n}\n"
JAVA_MODE1 = "package org.acme.core;\npublic enum OutputMode {\n  FLAT, STACKED, TILED\n}\n"
JAVA_OPTS = ("package org.acme.render;\npublic class RenderOptions {\n  public int tiles() { return 1; }\n"
             "  public RenderOptions withTiles(int n) { return this; }\n}\n")
JAVA_TARGET = "package org.acme.render;\npublic class RenderTarget {\n  public String name() { return \"\"; }\n}\n"


def java_origin(root):
    return build_origin(root, "origin-j", [
        {"src/main/java/org/acme/core/Document.java": JAVA_DOC, "src/main/java/org/acme/core/OutputMode.java": JAVA_MODE0},
        {"docs/notes.md": "notes\n"},
        {"src/main/java/org/acme/render/RenderOptions.java": JAVA_OPTS,
         "src/main/java/org/acme/render/RenderTarget.java": JAVA_TARGET,
         "src/main/java/org/acme/core/OutputMode.java": JAVA_MODE1},
        {"README.md": "readme\n"},
    ])


def py_origin(root):
    return build_origin(root, "origin-p", [
        {"src/acme/__init__.py": "", "src/acme/core.py": "def f():\n    pass\n"},
        {"README.md": "r\n"},
        {"src/acme/csv_reader.py": "class CsvReader: ...\n", "src/acme/parser.py": "class P: ...\n",
         "src/acme/_private.py": "x = 1\n", "tests/test_x.py": "pass\n"},
        {"CHANGELOG.md": "- csv reader\n"},
    ])


def cs_origin(root):
    return build_origin(root, "origin-c", [
        {"src/Acme.Sheets/Workbook.cs": "namespace Acme.Sheets { public class Workbook {} }\n"},
        {"docs/a.md": "a\n"},
        {"src/Acme.Sheets/ChartPalette.cs": "namespace Acme.Sheets { public class ChartPalette {} }\n",
         "src/Acme.Sheets/Internal/Helper.cs": "namespace X { class Helper {} }\n"},
        {"CHANGELOG.md": "- palette\n"},
    ])


class ToyJavaAdapter(la.LanguageAdapter):
    """GT-1 stand-in: derives a javap-shaped delta from the real git objects of two refs."""

    platform = "java"
    ground_truth_tier = la.GT1

    @staticmethod
    def _surface(repo, ref, runner):
        names = runner(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref]).stdout.split()
        out = {}
        for n in names:
            if not n.endswith(".java"):
                continue
            src = runner(["git", "-C", str(repo), "show", f"{ref}:{n}"]).stdout
            pkg = re.search(r"package ([\w.]+);", src).group(1)
            kind, name = re.search(r"public (class|enum) (\w+)", src).groups()
            members = {f"public {m[0]} {m[1]}(...);" for m in re.findall(r"public ([\w.]+) (\w+)\(", src)}
            consts = set()
            if kind == "enum":
                consts = {c.strip() for c in re.search(r"\{(.*?)\}", src, re.S).group(1).split(",") if c.strip()}
            out[f"{pkg}.{name}"] = {"members": members, "consts": consts, "enum": kind == "enum"}
        return out

    def api_delta(self, old_ref, new_ref, *, repo_path, runner):
        old, new = self._surface(repo_path, old_ref, runner), self._surface(repo_path, new_ref, runner)
        added = [{"type": t, "members": len(new[t]["members"]), "member_list": sorted(new[t]["members"]),
                  "is_enum": new[t]["enum"]} for t in sorted(set(new) - set(old))]
        changed = {}
        for t in sorted(set(new) & set(old)):
            consts = sorted(new[t]["consts"] - old[t]["consts"])
            members = sorted(new[t]["members"] - old[t]["members"])
            if consts or members:
                changed[t] = {"added": members + [f"public static final {t} {c};" for c in consts],
                              "removed": [], "enum_constants_added": consts, "enum_constants_removed": []}
        return {"ground_truth_tier": la.GT1, "method": "toy", "added_types": added, "removed_types": [],
                "changed_types": changed}


# ── content fixtures ─────────────────────────────────────────────────────────────────────────────

SURF = {"reference": "reference.aspose.org/en/{f}/{p}", "docs": "docs.aspose.org/en/{f}/{p}",
        "kb": "kb.aspose.org/en/{f}/{p}", "blog": "blog.aspose.org/{f}/{p}",
        "products": "products.aspose.org/en/{f}/{p}"}


def page(body, *, apis=(), title="T"):
    ev = "".join(f"    - {a}\n" for a in apis)
    return f"---\ntitle: {title}\nevidence:\n  apis:\n{ev}  claims: []\n---\n{body}\n"


def put(root: Path, surface, family, platform, rel, text):
    p = root / SURF[surface].format(f=family, p=platform) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def put_raw(root: Path, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def scan_one(unit, root, family, platform, criteria=None):
    crit = criteria or CRIT
    roots = pa.surface_roots(root, family, platform, crit)
    return pa.scan_content_presence([unit], roots, criteria=crit, locales=pa.discover_locale_codes(root, crit))[unit["id"]]


def mk_unit(uid, symbols, formats=()):
    return {"id": uid, "symbols": list(symbols), "formats": list(formats)}


# ═══ criteria ════════════════════════════════════════════════════════════════════════════════════

class TestCriteria:
    def test_defaults_are_valid(self):
        assert pa.validate_criteria(pa.DEFAULT_CRITERIA) == []
        assert pa.load_criteria() == pa.DEFAULT_CRITERIA

    def test_yaml_overlay_merges_over_defaults(self, tmp_path):
        f = tmp_path / "c.yaml"
        f.write_text("schema_version: 1\nworth_mentioning:\n  min_action: update\n  min_units: 2\n", encoding="utf-8")
        c = pa.load_criteria(f)
        assert c["worth_mentioning"]["min_action"] == "update" and c["worth_mentioning"]["min_units"] == 2
        assert c["worth_mentioning"]["surfaces"] == pa.DEFAULT_CRITERIA["worth_mentioning"]["surfaces"]
        assert c["content_gap"] == pa.DEFAULT_CRITERIA["content_gap"]

    @pytest.mark.parametrize("text,needle", [
        ("bogus: 1\n", "bogus: unknown key"),
        ("worth_mentioning:\n  nope: 1\n", "worth_mentioning.nope: unknown key"),
        ("worth_mentioning:\n  min_units: many\n", "worth_mentioning.min_units: expected int"),
        ("content_gap:\n  max_coverage_ratio: true\n", "content_gap.max_coverage_ratio"),
        ("analysable:\n  tiers: GT-1\n", "analysable.tiers: expected list"),
    ])
    def test_loader_rejects_schema_violations(self, tmp_path, text, needle):
        f = tmp_path / "c.yaml"
        f.write_text(text, encoding="utf-8")
        with pytest.raises(pa.CriteriaError, match=re.escape(needle)):
            pa.load_criteria(f)

    @pytest.mark.parametrize("text,needle", [
        ("worth_mentioning:\n  min_action: none\n", "min_action"),
        ("worth_mentioning:\n  surfaces: [docs, nowhere]\n", "unknown surface"),
        ("content_gap:\n  max_coverage_ratio: 1.5\n", "within (0, 1]"),
        ("content_gap:\n  max_coverage_ratio: 0\n", "within (0, 1]"),
        ("drift:\n  main_release_states: [released, nowhere]\n", "unknown release state"),
        ("ranking:\n  order: [release_triggered, product]\n", "ranking.order must be a permutation"),
        ("ranking:\n  release_state_order: [unreleased_main, nowhere]\n", "unknown release state"),
        ("ranking:\n  release_state_order: [unknown, unknown]\n", "duplicate"),
        ("gt2:\n  min_added_api_files: 0\n", ">= 1"),
        ("scan:\n  surface_paths:\n    nowhere: [x]\n", "unknown surface"),
    ])
    def test_loader_rejects_out_of_range_values(self, tmp_path, text, needle):
        f = tmp_path / "c.yaml"
        f.write_text(text, encoding="utf-8")
        with pytest.raises(pa.CriteriaError, match=re.escape(needle)):
            pa.load_criteria(f)

    def test_missing_file_is_an_error_and_digest_is_stable(self, tmp_path):
        with pytest.raises(pa.CriteriaError):
            pa.load_criteria(tmp_path / "absent.yaml")
        assert pa.criteria_digest(CRIT) == pa.criteria_digest(copy.deepcopy(CRIT))
        changed = copy.deepcopy(CRIT)
        changed["worth_mentioning"]["min_units"] = 3
        assert pa.criteria_digest(changed) != pa.criteria_digest(CRIT)


# ═══ small pure helpers ══════════════════════════════════════════════════════════════════════════

class TestHelpers:
    @pytest.mark.parametrize("text,expected", [
        ("---\ntitle: a\n---\nbody", "body"),
        ("---\n---\nbody", "body"),
        ("+++\ntitle = 'a'\n+++\nbody", "body"),
        ("﻿---\r\ntitle: a\r\n---\r\nbody", "body"),
        ("no frontmatter\n---\nrule\n", "no frontmatter\n---\nrule\n"),
        ("---\ntitle: a\n", "---\ntitle: a\n"),
    ])
    def test_strip_frontmatter(self, text, expected):
        assert pa.strip_frontmatter(text) == expected

    @pytest.mark.parametrize("pub,base,expected", [
        ("26.8.0", "26.7.0", True), ("v2.0", "1.9.9", True), ("1.0.0", "1.0.0", False), ("1.0", "1.0.0", False),
        ("1.0.0", "1.0.1", False), ("2.0.0-rc1", "1.0.0", True), (None, "1.0.0", None), ("1.0.0", None, None),
        ("latest", "1.0.0", None),
    ])
    def test_new_release(self, pub, base, expected):
        assert pa.compute_new_release(pub, base) is expected

    def test_model_fields_line_scan(self, tmp_path):
        write_model(tmp_path, "f", "p", "a" * 40, "3.4.5")
        m = pa.read_model_fields(tmp_path / "f" / "p" / "merged" / "model.yaml")
        assert m == {"exists": True, "repo_sha": "a" * 40, "version": "3.4.5"}
        assert pa.read_model_fields(tmp_path / "nope.yaml") == {"exists": False, "repo_sha": None, "version": None}


# ═══ L3 content-presence scan ════════════════════════════════════════════════════════════════════

class TestContentScan:
    def test_present_and_absent_per_surface(self, tmp_path):
        put(tmp_path, "docs", "f", "p", "a.md", page("Use `RenderOptions` to tile output."))
        put(tmp_path, "kb", "f", "p", "b.md", page("How to call RenderOptions in code."))
        put(tmp_path, "reference", "f", "p", "ns/ro.md", page("# RenderOptions\nRenderTarget too"))
        u = mk_unit("CU-1", ["org.acme.render::RenderOptions", "org.acme.render::RenderTarget"])
        r = scan_one(u, tmp_path, "f", "p")
        assert r["presence"]["docs"]["present_count"] == 1 and r["presence"]["docs"]["terms_total"] == 2
        assert r["presence"]["docs"]["files"] == ["a.md"]
        assert r["presence"]["kb"]["files"] == ["b.md"]
        assert r["presence"]["reference"]["present_count"] == 2
        assert r["absent_from"] == ["blog", "products"]
        assert r["content_gap"] is False  # present in docs and kb

    def test_gap_when_absent_from_all_four_even_if_reference_has_it(self, tmp_path):
        put(tmp_path, "reference", "f", "p", "x.md", page("RenderOptions reference page"))
        put(tmp_path, "docs", "f", "p", "other.md", page("nothing relevant"))
        r = scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")
        assert r["content_gap"] is True
        assert "reference" not in r["absent_from"] and r["presence"]["reference"]["present_count"] == 1
        assert r["absent_from"] == ["blog", "docs", "kb", "products"]

    def test_frontmatter_evidence_does_not_count(self, tmp_path):
        put(tmp_path, "docs", "f", "p", "ev.md", page("Body that never names it.", apis=["RenderOptions", "RenderTarget"],
                                                      title="RenderOptions"))
        put(tmp_path, "kb", "f", "p", "ev2.md", "---\ndescription: RenderOptions\n---\nplain body\n")
        r = scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")
        assert r["presence"]["docs"]["present_count"] == 0 and r["presence"]["kb"]["present_count"] == 0
        assert r["content_gap"] is True
        put(tmp_path, "docs", "f", "p", "ev.md", page("Now the body names RenderOptions.", apis=["RenderOptions"]))
        assert scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")["content_gap"] is False

    def test_locale_files_and_directories_are_excluded(self, tmp_path):
        put(tmp_path, "blog", "f", "p", "post/index.fr.md", page("RenderOptions"))
        put(tmp_path, "blog", "f", "p", "post/index.zh.md", page("RenderOptions"))
        put(tmp_path, "docs", "f", "p", "guide.de.md", page("RenderOptions"))
        put(tmp_path, "docs", "f", "p", "fr/guide.md", page("RenderOptions"))   # top-level locale dir of the surface
        put_raw(tmp_path, "docs.aspose.org/fr/f/p/guide.md", page("RenderOptions"))  # a locale tree beside `en`
        put(tmp_path, "docs", "f", "p", "x.md", page("nothing"))
        r = scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")
        assert r["content_gap"] is True and r["absent_from"] == ["blog", "docs", "kb", "products", "reference"]
        # a platform-looking dotted name is NOT a locale; the English `.en.md` file counts
        put(tmp_path, "docs", "f", "p", "howto.net.md", page("RenderOptions in a how-to"))
        r2 = scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")
        assert r2["presence"]["docs"]["files"] == ["howto.net.md"]
        put(tmp_path, "blog", "f", "p", "post2/index.en.md", page("RenderOptions"))
        assert scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")["presence"]["blog"]["files"] == ["post2/index.en.md"]

    def test_discovered_locale_directories_extend_the_configured_codes(self, tmp_path):
        (tmp_path / "docs.aspose.org" / "xx").mkdir(parents=True)
        (tmp_path / "docs.aspose.org" / "en").mkdir()
        codes = pa.discover_locale_codes(tmp_path, CRIT)
        assert "xx" in codes and "en" not in codes and "fr" in codes
        put(tmp_path, "docs", "f", "p", "guide.xx.md", page("RenderOptions"))
        assert scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")["content_gap"] is True

    def test_files_are_capped_and_sorted(self, tmp_path):
        for i in (7, 3, 9, 1, 5, 2, 8):
            put(tmp_path, "docs", "f", "p", f"p{i}.md", page("RenderOptions"))
        r = scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")
        assert r["presence"]["docs"]["files"] == ["p1.md", "p2.md", "p3.md", "p5.md", "p7.md"]
        assert r["presence"]["docs"]["files_scanned"] == 7

    def test_member_requires_its_owner_in_the_same_file(self, tmp_path):
        put(tmp_path, "docs", "f", "p", "a.md", page("We call markdownText() on something."))
        u = mk_unit("CU-1", ["a.b::Document.markdownText"])
        assert scan_one(u, tmp_path, "f", "p")["content_gap"] is True
        put(tmp_path, "kb", "f", "p", "b.md", page("Use `Document.markdownText()` to get the text."))
        assert scan_one(u, tmp_path, "f", "p")["presence"]["kb"]["present_count"] == 1

    def test_single_word_type_names_need_a_code_context(self, tmp_path):
        put(tmp_path, "docs", "f", "p", "a.md", page("The Value of a Document is shown on the Page."))
        u = mk_unit("CU-1", ["a::Value", "a::Page"])
        assert scan_one(u, tmp_path, "f", "p")["content_gap"] is True
        put(tmp_path, "kb", "f", "p", "b.md", page("```\nPage p = new Page();\n```"))
        assert scan_one(u, tmp_path, "f", "p")["presence"]["kb"]["present_count"] == 1

    def test_plain_lowercase_terms_match_only_in_code(self, tmp_path):
        put(tmp_path, "docs", "f", "p", "a.md", page("The parser reads the parser tokens."))
        u = mk_unit("FH-1", ["parser"])
        assert scan_one(u, tmp_path, "f", "p")["content_gap"] is True
        put(tmp_path, "kb", "f", "p", "b.md", page("Call `parser` here.\n"))
        put(tmp_path, "blog", "f", "p", "c.md", page("```\nimport parser\n```"))
        r = scan_one(u, tmp_path, "f", "p")
        assert r["presence"]["kb"]["present_count"] == 1 and r["presence"]["blog"]["present_count"] == 1

    def test_whole_identifier_match_not_substring(self, tmp_path):
        put(tmp_path, "docs", "f", "p", "a.md", page("RenderOptionsBuilder and MyRenderOptions are different names."))
        assert scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "f", "p")["content_gap"] is True

    def test_qualified_hit_and_keywords_are_reported_not_decisive(self, tmp_path):
        put(tmp_path, "docs", "f", "p", "a.md", page("Import org.acme.render.RenderOptions then tile the output."))
        r = scan_one(mk_unit("CU-1", ["org.acme.render::RenderOptions"]), tmp_path, "f", "p")
        assert r["presence"]["docs"]["qualified_hits"] == ["org.acme.render.RenderOptions"]
        # keywords alone (no symbol) never remove a gap
        put(tmp_path, "kb", "f", "p", "k.md", page("Rendering and options are described in prose; tile settings."))
        r2 = scan_one(mk_unit("CU-2", ["org.acme.render::RenderTarget"]), tmp_path, "f", "p")
        assert r2["content_gap"] is True
        assert "render" in r2["keywords"] and "target" in r2["keywords"]
        r3 = scan_one(mk_unit("CU-3", ["org.acme.render::RenderOptions"]), tmp_path, "f", "p")
        assert "options" in r3["presence"]["kb"]["keyword_hits"]

    def test_missing_content_dirs_scan_as_empty(self, tmp_path):
        r = scan_one(mk_unit("CU-1", ["a::RenderOptions"]), tmp_path, "nofam", "noplat")
        assert r["content_gap"] is True and all(r["presence"][s]["files_scanned"] == 0 for s in pa.SURFACES)


# ═══ analyze_product: three repository shapes ════════════════════════════════════════════════════

class TestAnalyzeJavaShape:
    """GT-1 adapter, enum constant + new option classes, baseline from the knowledge sha (assumed)."""

    def setup_world(self, tmp_path):
        origin, shas = java_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        kroot = tmp_path / "knowledge"
        write_model(kroot, "fam", "java", shas[0], "1.0.0")
        content = tmp_path / "content"
        put(content, "docs", "fam", "java", "render.md", page("Use `RenderOptions` and `RenderTarget`.", apis=["OutputMode"]))
        put(content, "kb", "fam", "java", "k.md", page("nothing about it"))
        return origin, shas, clone, kroot, content

    def test_baseline_is_made_reachable_and_units_found(self, tmp_path):
        origin, shas, clone, kroot, content = self.setup_world(tmp_path)
        assert not is_ancestor(clone, shas[0])                       # depth 2: the baseline is NOT there yet
        head_before = git(clone, "rev-parse", "HEAD")
        reach = Reach()
        res = pa.analyze_product("fam", "java", repo_path=clone, content_root=content, knowledge_root=kroot,
                                 adapter=ToyJavaAdapter(), ensure_reachable=reach)
        assert reach.calls == [shas[0]] and is_ancestor(clone, shas[0])      # deepened via core.clone_cache
        assert res["status"] == "OK" and res["error"] is None
        assert res["baseline"] == {"ref": shas[0], "source": "knowledge_sha", "assumed": True, "version": "1.0.0",
                                   "reachable": True, "reachability": "reachable"}
        assert res["head"] == {"ref": shas[3], "source": "refs/remotes/origin/HEAD"}
        assert res["ground_truth_tier"] == "GT-1" and res["symbol_level"] is True and res["api_surface_touched"] is True
        by_sym = {tuple(u["symbols"]): u for u in res["units"]}
        types_unit = next(u for u in res["units"] if "org.acme.render::RenderOptions" in u["symbols"])
        const_unit = next(u for u in res["units"] if "org.acme.core::OutputMode.TILED" in u["symbols"])
        assert sorted(s for s in types_unit["symbols"] if "." not in s.split("::")[-1]) == [
            "org.acme.render::RenderOptions", "org.acme.render::RenderTarget"]
        assert len(by_sym) == 2
        # RenderOptions/Target are named in docs; the enum-constant unit never is (evidence-only mention)
        assert types_unit["scan"]["content_gap"] is False
        assert types_unit["scan"]["absent_from"] == ["blog", "kb", "products", "reference"]
        assert const_unit["scan"]["content_gap"] is True
        assert const_unit["placement_summary"]["products"] == "mention"
        # read-only: same HEAD, clean tree, no checkout
        assert git(clone, "rev-parse", "HEAD") == head_before
        assert git(clone, "status", "--porcelain") == ""

    def test_deterministic_and_volatile_isolated(self, tmp_path):
        _o, _s, clone, kroot, content = self.setup_world(tmp_path)
        kw = dict(repo_path=clone, content_root=content, knowledge_root=kroot, adapter=ToyJavaAdapter())
        a = pa.analyze_product("fam", "java", now="2026-10-07T00:00:00Z", **kw)
        b = pa.analyze_product("fam", "java", now="2030-01-01T00:00:00Z", **kw)
        assert a["volatile"] != b["volatile"]
        assert pa.dumps(pa.canonical_for_compare(a)) == pa.dumps(pa.canonical_for_compare(b))

    def test_state_propagated_sha_beats_knowledge_sha_and_head_override(self, tmp_path):
        _o, shas, clone, kroot, content = self.setup_world(tmp_path)
        state = {"content_propagated_sha": shas[1]}
        res = pa.analyze_product("fam", "java", repo_path=clone, content_root=content, knowledge_root=kroot,
                                 adapter=ToyJavaAdapter(), state_reader=lambda f, p: state, head_ref=shas[2])
        assert res["baseline"]["source"] == "content_propagated_sha" and res["baseline"]["ref"] == shas[1]
        assert res["baseline"]["assumed"] is False and res["baseline"]["version"] is None
        assert res["head"] == {"ref": shas[2], "source": "explicit"}
        assert res["propagation"]["status"] == "DRIFTED"
        explicit = pa.analyze_product("fam", "java", repo_path=clone, content_root=content, knowledge_root=kroot,
                                      adapter=ToyJavaAdapter(), state_reader=lambda f, p: state, base_ref=shas[0])
        assert explicit["baseline"]["source"] == "explicit" and explicit["baseline"]["assumed"] is False

    def test_baseline_equal_head_is_a_clean_no_change(self, tmp_path):
        _o, shas, clone, kroot, content = self.setup_world(tmp_path)
        res = pa.analyze_product("fam", "java", repo_path=clone, content_root=content, knowledge_root=kroot,
                                 base_ref=shas[3], adapter=ToyJavaAdapter())
        assert res["status"] == "OK" and res["units"] == [] and res["api_surface_touched"] is False
        assert res["method"] == "no_change"
        ev = pa.evaluate_candidate(res, CRIT)
        assert ev["candidate"] is False

    def test_adapter_failure_falls_back_to_gt2_and_says_so(self, tmp_path):
        _o, _s, clone, kroot, content = self.setup_world(tmp_path)

        class Boom(ToyJavaAdapter):
            def api_delta(self, *a, **k):
                raise la.AdapterUnavailable("no toolchain here")

        res = pa.analyze_product("fam", "java", repo_path=clone, content_root=content, knowledge_root=kroot,
                                 adapter=Boom())
        assert res["status"] == "OK" and res["ground_truth_tier"] == "GT-2" and res["symbol_level"] is False
        assert res["fallback"]["from"] == "GT-1" and "no toolchain" in res["fallback"]["reason"]
        assert res["units"] == [] and res["api_surface_touched"] is True
        assert {h["symbols"][0] for h in res["file_hints"]} == {"RenderOptions", "RenderTarget"}


class TestAnalyzePythonShape:
    """Real GT-2 adapter; baseline from the propagation state; hints with lowercase + underscore stems."""

    def test_file_hints_from_added_api_files(self, tmp_path):
        origin, shas = py_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        content = tmp_path / "content"
        put(content, "docs", "fam", "py", "g.md", page("The parser reads tokens in prose only."))
        put(content, "kb", "fam", "py", "k.md", page("Use `csv_reader` for CSV input."))
        reach = Reach()
        res = pa.analyze_product("fam", "py", repo_path=clone, content_root=content, knowledge_root=tmp_path / "k",
                                 state_reader=lambda f, p: {"content_propagated_sha": shas[0]},
                                 adapter=la.adapter_for("python"), ensure_reachable=reach)
        assert reach.calls == [shas[0]]
        assert res["status"] == "OK" and res["ground_truth_tier"] == "GT-2" and res["symbol_level"] is False
        assert res["units"] == [] and res["method"] == "adapter"
        stems = {h["symbols"][0]: h for h in res["file_hints"]}
        assert set(stems) == {"csv_reader", "parser"}               # _private.py and tests/ never hint
        assert stems["csv_reader"]["scan"]["content_gap"] is False  # in kb code
        assert stems["parser"]["scan"]["content_gap"] is True       # only the dictionary word, in prose
        assert res["changed_files"]["counts"]["added_source"] == 3
        assert any(n.startswith("GT-2") for n in res["notes"])

    def test_candidate_via_hints_and_covered_via_hints(self, tmp_path):
        origin, shas = py_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        content = tmp_path / "content"
        rel = {"release_state": "unreleased_main", "published_version": None}
        kw = dict(repo_path=clone, content_root=content, knowledge_root=tmp_path / "k", base_ref=shas[0],
                  adapter=la.adapter_for("python"), release_info=rel)
        res = pa.analyze_product("fam", "py", **kw)
        ev = pa.evaluate_candidate(res, CRIT)
        assert ev["candidate"] is True and ev["criteria"]["2_worth_mentioning"]["evidence"]["evidence_tier"] == "GT-2-file-level"
        assert ev["gap_units"] == 2 and ev["release_triggered"] is False and ev["api_touched"] is True
        put(content, "docs", "fam", "py", "all.md", page("Use `csv_reader` and `parser` together."))
        covered = pa.evaluate_candidate(pa.analyze_product("fam", "py", **kw), CRIT)
        assert covered["candidate"] is False and covered["classification"] == "COVERED"


class TestAnalyzeCSharpShape:
    def test_gt2_net_tree(self, tmp_path):
        origin, shas = cs_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        content = tmp_path / "content"
        put(content, "products", "fam", "net", "p.md", page("A page about workbooks."))
        res = pa.analyze_product("fam", "net", repo_path=clone, content_root=content, knowledge_root=tmp_path / "k",
                                 base_ref=shas[0], adapter=la.adapter_for("net"), ensure_reachable=Reach(),
                                 release_info=lambda head: {"release_state": "unreleased_main",
                                                            "published_version": "2.0.0"})
        assert res["status"] == "OK" and res["ground_truth_tier"] == "GT-2"
        assert [h["symbols"][0] for h in res["file_hints"]] == ["ChartPalette"]   # Internal/ never hints
        assert res["api_surface_touched"] is True
        ev = pa.evaluate_candidate(res, CRIT)
        assert ev["candidate"] is True
        assert res["release"]["new_release"] is None                               # baseline version unknown
        assert ev["criteria"]["1_drift_release"]["evidence"]["trigger"] == "main_api_touched"


class TestUnreachableAndMissing:
    def test_orphaned_baseline_through_the_real_deepening_path(self, tmp_path):
        origin, shas = java_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        reach = Reach()
        orphan = "deadbeef" * 5
        res = pa.analyze_product("fam", "java", repo_path=clone, content_root=tmp_path / "c", base_ref=orphan,
                                 adapter=ToyJavaAdapter(), ensure_reachable=reach)
        assert reach.calls == [orphan]
        assert res["status"] == "ORPHANED_BASELINE" and res["baseline"]["reachable"] is False
        assert res["units"] == [] and res["error"]
        ev = pa.evaluate_candidate(res, CRIT)
        assert ev["candidate"] is False and ev["classification"] == "ORPHANED_BASELINE"
        assert git(clone, "status", "--porcelain") == ""

    def test_injected_seam_false_is_orphaned_never_a_crash(self, tmp_path):
        origin, shas = py_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        res = pa.analyze_product("fam", "py", repo_path=clone, content_root=tmp_path / "c", base_ref=shas[0],
                                 ensure_reachable=lambda repo, sha: False)
        assert res["status"] == "ORPHANED_BASELINE"

    def test_no_baseline_and_missing_repo(self, tmp_path):
        origin, _ = py_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        res = pa.analyze_product("fam", "py", repo_path=clone, content_root=tmp_path / "c", knowledge_root=tmp_path / "k")
        assert res["status"] == "NO_BASELINE"
        res2 = pa.analyze_product("fam", "py", content_root=tmp_path / "c", base_ref="a" * 40, head_ref="b" * 40)
        assert res2["status"] == "ERROR" and "repo_path" in res2["error"]

    def test_unresolvable_head_is_an_error_status(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        git(empty, "init", "-q")
        res = pa.analyze_product("fam", "py", repo_path=empty, content_root=tmp_path / "c", base_ref="a" * 40)
        assert res["status"] == "ERROR" and "head" in res["error"]


class TestReachabilityStates:
    """Only a REACHABLE / ORPHANED verdict may yield OK / ORPHANED_BASELINE; UNKNOWN is never an orphan."""

    def run(self, tmp_path, ensure, *, clone=None, base_ref=None):
        origin, shas = py_origin(tmp_path)
        clone = clone or shallow_clone(origin, tmp_path / "clone")
        # base = the (already present) head commit: a fake seam that says "reachable" must not need a deepen
        return pa.analyze_product("fam", "py", repo_path=clone, content_root=tmp_path / "c",
                                  base_ref=base_ref or shas[3], adapter=la.adapter_for("python"),
                                  ensure_reachable=ensure), clone

    @pytest.mark.parametrize("verdict,status", [
        ("reachable", "OK"), ("orphaned", "ORPHANED_BASELINE"), ("unknown", "BASELINE_UNVERIFIABLE"),
        (True, "OK"), (False, "ORPHANED_BASELINE"),
        (None, "BASELINE_UNVERIFIABLE"), ("weird", "BASELINE_UNVERIFIABLE"),
    ])
    def test_seam_verdict_to_status(self, tmp_path, verdict, status):
        res, _ = self.run(tmp_path, lambda repo, sha: verdict)
        assert res["status"] == status

    def test_unknown_is_an_explicit_non_orphan_non_ok_status(self, tmp_path):
        res, _ = self.run(tmp_path, lambda repo, sha: "unknown")
        assert res["status"] == "BASELINE_UNVERIFIABLE" and res["status"] not in ("OK", "ORPHANED_BASELINE")
        assert res["baseline"]["reachability"] == "unknown" and res["baseline"]["reachable"] is None
        assert res["units"] == [] and res["file_hints"] == [] and "unorphaned" not in (res["error"] or "")
        ev = pa.evaluate_candidate(res, CRIT)
        assert ev["candidate"] is False and ev["classification"] == "BASELINE_UNVERIFIABLE"
        orphan, _ = self.run(tmp_path / "o", lambda repo, sha: "orphaned")
        assert orphan["baseline"]["reachability"] == "orphaned" and orphan["baseline"]["reachable"] is False

    def test_exhausted_fetch_cap_is_unverifiable_not_orphaned_and_leaves_the_clone_alone(self, tmp_path):
        cc.configure(max_deepen_fetches=0)                      # the real default seam hits the cap immediately
        origin, shas = py_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        head = git(clone, "rev-parse", "HEAD")
        res = pa.analyze_product("fam", "py", repo_path=clone, content_root=tmp_path / "c", base_ref=shas[0],
                                 adapter=la.adapter_for("python"))
        assert res["status"] == "BASELINE_UNVERIFIABLE" and res["baseline"]["reachability"] == "unknown"
        assert git(clone, "rev-parse", "HEAD") == head and git(clone, "status", "--porcelain") == ""
        cc.configure()                                           # defaults back, memo cleared
        again = pa.analyze_product("fam", "py", repo_path=clone, content_root=tmp_path / "c", base_ref=shas[0],
                                   adapter=la.adapter_for("python"))
        assert again["status"] == "OK" and again["baseline"]["reachability"] == "reachable"

    def test_a_definitive_orphan_still_reports_orphaned(self, tmp_path):
        origin, _ = py_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "clone")
        res = pa.analyze_product("fam", "py", repo_path=clone, content_root=tmp_path / "c", base_ref="deadbeef" * 5,
                                 adapter=la.adapter_for("python"))
        assert res["status"] == "ORPHANED_BASELINE" and res["baseline"]["reachability"] == "orphaned"

    def test_tests_do_not_leak_the_fetch_cap(self, tmp_path):
        # each shallow clone needs >= 2 fetches; 8 of them would exceed the default cap of 12 without the reset
        for i in range(8):
            origin, shas = py_origin(tmp_path / f"w{i}")
            clone = shallow_clone(origin, tmp_path / f"w{i}" / "clone")
            cc.reset_deepen_state()
            res = pa.analyze_product("fam", "py", repo_path=clone, content_root=tmp_path / "c", base_ref=shas[0],
                                     adapter=la.adapter_for("python"))
            assert res["status"] == "OK", i


# ═══ bundles ═════════════════════════════════════════════════════════════════════════════════════

def write_bundle(d: Path, entries, sha, version="1.0.0", formats=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
    (d / "formats.json").write_text(json.dumps(formats or []), encoding="utf-8")
    (d / "model.yaml").write_text(f"version: {version}\nrepo_sha: {sha}\n", encoding="utf-8")


def m(name, *params, ret=""):
    return {"name": name, "params": [{"name": f"a{i}", "type": t} for i, t in enumerate(params)], "return_type": ret}


JAVA_B_OLD = [
    {"name": "Document", "kind": "class_declaration", "class_package": "org.acme.core", "methods": [m("save")],
     "properties": [], "enum_members": []},
    {"name": "OutputMode", "kind": "enum_declaration", "class_package": "org.acme.core", "methods": [],
     "properties": [], "enum_members": ["FLAT", "STACKED"]},
]
NET_B_OLD = [
    {"name": "Workbook", "kind": "class", "namespace": "Acme.Sheets", "methods": [m("Open")], "properties": [], "enum_members": []},
    {"name": "Chart", "kind": "class", "namespace": "Acme.Sheets.Charts", "methods": [], "properties": [{"name": "Title"}],
     "enum_members": []},
]
PY_B_OLD = [
    {"name": "Sheet", "kind": "class", "file": "acme/core/sheet.py", "methods": [m("read")], "properties": [], "enum_members": []},
]


def mutate(entries, kind):
    new = copy.deepcopy(entries)
    if kind == "java":
        new[0]["methods"].append(m("markdownText", ret="String"))
        new[1]["enum_members"].append("TILED")
        new += [{"name": "RenderOptions", "kind": "class_declaration", "class_package": "org.acme.render",
                 "methods": [m("tiles"), m("withTiles", "int", ret="RenderOptions")], "properties": [], "enum_members": []},
                {"name": "RenderTarget", "kind": "class_declaration", "class_package": "org.acme.render",
                 "methods": [m("name")], "properties": [], "enum_members": []}]
    elif kind == "net":
        new += [{"name": "ChartPalette", "kind": "class", "namespace": "Acme.Sheets.Charts",
                 "methods": [m("Apply", "Chart")], "properties": [], "enum_members": []},
                {"name": "Hidden", "kind": "class", "namespace": "Acme.Sheets", "visibility": "internal",
                 "methods": [], "properties": [], "enum_members": []}]
        new[0]["methods"].append(m("ApplyTheme", "ChartPalette"))
    else:
        new += [{"name": "CsvReader", "kind": "class", "file": "acme/imports/csv_reader.py", "methods": [m("read_rows")],
                 "properties": [], "enum_members": []}]
        new.pop(0)  # removal is counted, never a unit
    return new


class TestBundles:
    @pytest.mark.parametrize("kind,old,pkg_symbol", [
        ("java", JAVA_B_OLD, "org.acme.render::RenderOptions"),
        ("net", NET_B_OLD, "Acme.Sheets.Charts::ChartPalette"),
        ("py", PY_B_OLD, "acme/imports/csv_reader.py::CsvReader"),
    ])
    def test_bundle_delta_units_and_scan(self, tmp_path, kind, old, pkg_symbol):
        write_bundle(tmp_path / "old", old, "1" * 40, "1.0.0")
        write_bundle(tmp_path / "new", mutate(old, kind), "2" * 40, "1.1.0")
        content = tmp_path / "content"
        name = pkg_symbol.split("::")[1]
        put(content, "docs", "fam", "plat", "a.md", page(f"We document `{name}` here."))
        res = pa.analyze_product("fam", "plat", bundles=(tmp_path / "old", tmp_path / "new"), content_root=content,
                                 knowledge_root=tmp_path / "k",
                                 release_info={"release_state": "released", "published_version": "1.1.0"})
        assert res["status"] == "OK" and res["method"] == "bundles" and res["ground_truth_tier"] == "KNOWLEDGE"
        assert res["baseline"]["ref"] == "1" * 40 and res["head"]["ref"] == "2" * 40
        assert res["baseline"]["version"] == "1.0.0"
        assert res["release"]["new_release"] is True                   # published 1.1.0 > baseline 1.0.0
        syms = {s for u in res["units"] for s in u["symbols"]}
        assert pkg_symbol in syms
        assert not any("Hidden" in s for s in syms)
        assert res["api_surface_touched"] is True
        unit = next(u for u in res["units"] if pkg_symbol in u["symbols"])
        assert unit["scan"]["content_gap"] is False
        assert "docs" not in unit["scan"]["absent_from"]

    def test_new_release_evaluated_from_versions(self, tmp_path):
        write_bundle(tmp_path / "old", JAVA_B_OLD, "1" * 40, "1.0.0")
        write_bundle(tmp_path / "new", mutate(JAVA_B_OLD, "java"), "2" * 40, "1.1.0")
        res = pa.analyze_product("fam", "plat", bundles=(tmp_path / "old", tmp_path / "new"), content_root=tmp_path / "c",
                                 release_info={"release_state": "released", "published_version": "1.1.0"})
        assert res["release"]["new_release"] is True
        ev = pa.evaluate_candidate(res, CRIT)
        assert ev["candidate"] is True and ev["release_triggered"] is True

    def test_delta_function_counts_removals_and_formats(self, tmp_path):
        write_bundle(tmp_path / "old", PY_B_OLD, "1" * 40, formats=[{"format": "AAA", "direction": "import", "functional": True}])
        write_bundle(tmp_path / "new", mutate(PY_B_OLD, "py"), "2" * 40,
                     formats=[{"format": "AAA", "direction": "import", "functional": True},
                              {"format": "BBB", "direction": "export", "functional": True},
                              {"format": "CCC", "direction": "detect", "functional": True},
                              {"format": "DDD", "direction": "import", "functional": False}])
        kd, fdl, surface, counts = pa.knowledge_delta_from_bundles(tmp_path / "old", tmp_path / "new")
        assert counts == {"new_types": 1, "removed_types": 1, "modified_types": 0}
        assert kd["new_apis_qualified"] == ["acme/imports/csv_reader.py::CsvReader"]
        assert fdl["formats_added"] == [{"name": "BBB", "ext": None}]
        assert len(surface) == 1

    def test_real_tracked_bundle_vs_mutated_copy(self, tmp_path):
        src = REPO_ROOT / "knowledge" / "pdf" / "java" / "merged"
        if not (src / "api_surface.json").is_file():
            pytest.skip("LOUD: tracked bundle knowledge/pdf/java/merged is missing in this checkout")
        old = tmp_path / "old"
        old.mkdir()
        for n in ("api_surface.json", "formats.json", "model.yaml"):
            shutil.copy2(src / n, old / n)
        entries = json.loads((old / "api_surface.json").read_text(encoding="utf-8"))
        new = copy.deepcopy(entries)
        new += [{"name": "ZzNewWidgetOptions", "kind": "class_declaration", "class_package": "org.zz.widget",
                 "methods": [m("tiles")], "properties": [], "enum_members": []},
                {"name": "ZzNewWidgetSaver", "kind": "class_declaration", "class_package": "org.zz.widget",
                 "methods": [m("save", "ZzNewWidgetOptions")], "properties": [], "enum_members": []}]
        enum_entry = next(e for e in new if e.get("enum_members"))
        enum_entry["enum_members"] = list(enum_entry["enum_members"]) + ["ZZ_NEW_CONSTANT"]
        write_bundle(tmp_path / "new", new, "9" * 40, "99.0.0")
        content = tmp_path / "content"
        put(content, "docs", "pdf", "java", "w.md", page("Documented `ZzNewWidgetOptions`."))
        res = pa.analyze_product("pdf", "java", bundles=(old, tmp_path / "new"), content_root=content,
                                 knowledge_root=tmp_path / "k")
        assert res["status"] == "OK"
        syms = {s for u in res["units"] for s in u["symbols"]}
        assert {"org.zz.widget::ZzNewWidgetOptions", "org.zz.widget::ZzNewWidgetSaver"} <= syms
        assert any(s.endswith(".ZZ_NEW_CONSTANT") for s in syms)
        widget = next(u for u in res["units"] if "org.zz.widget::ZzNewWidgetOptions" in u["symbols"])
        assert widget["scan"]["content_gap"] is False
        const = next(u for u in res["units"] if any(s.endswith(".ZZ_NEW_CONSTANT") for s in u["symbols"]))
        assert const["scan"]["content_gap"] is True
        assert len(res["units"]) == 2 and res["baseline"]["version"] == pa.read_model_fields(old / "model.yaml")["version"]


# ═══ criteria evaluation ═════════════════════════════════════════════════════════════════════════

def mk_unit_a(uid, *, products="mention", coverage=0.0, total=4):
    """A scanned unit whose NEW-type coverage on docs is `coverage` (primary_total new types)."""
    present = round(coverage * total)
    names = [f"T{i}" for i in range(total)]
    pres = {s: {"coverage": 0.0, "terms_total": total, "present_count": 0, "primary_present": []} for s in pa.SURFACES}
    pres["docs"].update(coverage=coverage, present_count=present, primary_present=names[:present])
    return {"id": uid, "title": uid, "symbols": [f"ns::{uid}"],
            "placement_summary": {"reference": "create", "docs": "none", "kb": "none", "blog": "none", "products": products},
            "scan": {"presence": pres, "absent_from": [], "coverage": {"basis": "new_types", "primary_total": total}}}


def mk_analysis(product, *, status="OK", propagation="UNRECORDED", new_release=None, release_state="unknown",
                touched=False, tier="GT-1", units=None, hints=None):
    family, platform = product.split("/")
    return {"product": product, "family": family, "platform": platform, "status": status, "error": None,
            "propagation": {"status": propagation}, "release": {"release_state": release_state, "new_release": new_release,
                                                                "published_version": "2", "baseline_version": "1"},
            "ground_truth_tier": tier, "symbol_level": tier == "GT-1", "api_surface_touched": touched, "method": "adapter",
            "baseline": {"ref": "a" * 40, "assumed": True}, "head": {"ref": "b" * 40},
            "units": units if units is not None else [mk_unit_a("U1")], "file_hints": hints or []}


class TestEvaluate:
    def test_candidate_by_release(self):
        ev = pa.evaluate_candidate(mk_analysis("f/a", new_release=True), CRIT)
        assert ev["candidate"] and ev["release_triggered"] and ev["classification"] == "candidate"
        assert ev["criteria"]["1_drift_release"]["evidence"]["trigger"] == "release"
        assert all(c["ok"] for c in ev["criteria"].values())

    def test_candidate_by_main_api_touch_only(self):
        ev = pa.evaluate_candidate(mk_analysis("f/a", release_state="unreleased_main", touched=True), CRIT)
        assert ev["candidate"] and not ev["release_triggered"] and ev["api_touched"]
        assert ev["criteria"]["1_drift_release"]["evidence"]["trigger"] == "main_api_touched"

    @pytest.mark.parametrize("kw,cls", [
        (dict(release_state="unreleased_main", touched=False), "NO_DRIFT_SIGNAL"),   # main moved, API untouched
        (dict(release_state="released", touched=True), "NO_DRIFT_SIGNAL"),           # API touched, but HEAD is the release
        (dict(new_release=False, release_state="released", touched=True), "NO_DRIFT_SIGNAL"),
        (dict(new_release=None), "NO_DRIFT_SIGNAL"),                                  # version comparison impossible
        (dict(new_release=True, propagation="PROPAGATED"), "NO_DRIFT_SIGNAL"),       # content already propagated
        (dict(new_release=True, tier="GT-9"), "NOT_ANALYSABLE"),
        (dict(new_release=True, tier=None), "NOT_ANALYSABLE"),
        (dict(new_release=True, units=[]), "NOT_WORTH_MENTIONING"),
        (dict(new_release=True, units=[mk_unit_a("U1", products="none")]), "NOT_WORTH_MENTIONING"),
        (dict(new_release=True, units=[mk_unit_a("U1", coverage=0.5)]), "COVERED"),
        (dict(new_release=True, status="ORPHANED_BASELINE"), "ORPHANED_BASELINE"),
        (dict(new_release=True, status="NO_BASELINE"), "NO_BASELINE"),
        (dict(new_release=True, status="ERROR"), "ERROR"),
        (dict(new_release=True, status="DEFERRED"), "DEFERRED"),
    ])
    def test_negative_outcomes(self, kw, cls):
        ev = pa.evaluate_candidate(mk_analysis("f/a", **kw), CRIT)
        assert ev["candidate"] is False and ev["classification"] == cls and ev["reasons"]

    def test_reference_only_placement_is_not_worth_mentioning(self):
        u = mk_unit_a("U1", products="none")
        assert u["placement_summary"]["reference"] == "create"
        assert pa.evaluate_candidate(mk_analysis("f/a", new_release=True, units=[u]), CRIT)["criteria"]["2_worth_mentioning"]["ok"] is False

    def test_thresholds_are_criteria_driven(self):
        weak = mk_analysis("f/a", new_release=True, units=[mk_unit_a("U1", products="mention")])
        strict = copy.deepcopy(CRIT)
        strict["worth_mentioning"]["min_action"] = "update"
        assert pa.evaluate_candidate(weak, strict)["classification"] == "NOT_WORTH_MENTIONING"
        two = copy.deepcopy(CRIT)
        two["worth_mentioning"]["min_units"] = 2
        assert pa.evaluate_candidate(weak, two)["classification"] == "NOT_WORTH_MENTIONING"
        gap2 = copy.deepcopy(CRIT)
        gap2["content_gap"]["min_gap_units"] = 2
        assert pa.evaluate_candidate(weak, gap2)["classification"] == "COVERED"
        narrow = copy.deepcopy(CRIT)
        narrow["drift"]["main_release_states"] = ["unreleased_main"]
        a = mk_analysis("f/a", release_state="unknown", touched=True)
        assert pa.evaluate_candidate(a, CRIT)["candidate"] is True and pa.evaluate_candidate(a, narrow)["candidate"] is False
        no_api = copy.deepcopy(CRIT)
        no_api["drift"]["require_api_touched_for_main"] = False
        b = mk_analysis("f/a", release_state="unreleased_main", touched=False)
        assert pa.evaluate_candidate(b, no_api)["candidate"] is True
        tiers = copy.deepcopy(CRIT)
        tiers["analysable"]["tiers"] = ["GT-1"]
        assert pa.evaluate_candidate(mk_analysis("f/a", new_release=True, tier="GT-2"), tiers)["classification"] == "NOT_ANALYSABLE"

    def test_gap_is_recomputed_with_the_criteria_in_force(self):
        a = mk_analysis("f/a", new_release=True, units=[mk_unit_a("U1", coverage=0.75)])
        assert pa.evaluate_candidate(a, CRIT)["classification"] == "COVERED"        # 0.75 >= 0.5
        loose = copy.deepcopy(CRIT)
        loose["content_gap"]["max_coverage_ratio"] = 0.8
        assert pa.evaluate_candidate(a, loose)["candidate"] is True                  # 0.75 < 0.8
        only_kb = copy.deepcopy(CRIT)
        only_kb["content_gap"]["gap_surfaces"] = ["kb"]                              # docs no longer counts
        assert pa.evaluate_candidate(a, only_kb)["candidate"] is True

    def test_gt2_hint_threshold(self):
        hint = {"id": "FH-1", "symbols": ["x"], "scan": mk_unit_a("x")["scan"]}
        a = mk_analysis("f/a", new_release=True, tier="GT-2", units=[], hints=[hint])
        assert pa.evaluate_candidate(a, CRIT)["candidate"] is True
        two = copy.deepcopy(CRIT)
        two["gt2"]["min_added_api_files"] = 2
        assert pa.evaluate_candidate(a, two)["classification"] == "NOT_WORTH_MENTIONING"


# ═══ ranking ═════════════════════════════════════════════════════════════════════════════════════

def ranking_fixture():
    two = [mk_unit_a("U1"), mk_unit_a("U2")]
    three = [mk_unit_a("U1"), mk_unit_a("U2"), mk_unit_a("U3")]
    return [
        mk_analysis("zz/rel-small", new_release=True, touched=False),                        # release, not API
        mk_analysis("aa/rel-touched", new_release=True, touched=True),                       # release + API
        mk_analysis("mm/main-three", release_state="unreleased_main", touched=True, units=three),
        mk_analysis("bb/main-two", release_state="unreleased_main", touched=True, units=two),
        mk_analysis("cc/main-two", release_state="unreleased_main", touched=True, units=two),  # tie with bb -> lexicographic
        mk_analysis("ee/covered", new_release=True, units=[mk_unit_a("U1", coverage=1.0)]),
        mk_analysis("ff/unknown-big", release_state="unknown", touched=True, units=[mk_unit_a(f"U{i}") for i in range(5)]),
        mk_analysis("gg/unknown-small", release_state="unknown", touched=True),
        mk_analysis("dd/propagated", new_release=True, propagation="PROPAGATED"),
    ]


class TestRanking:
    EXPECTED = ["aa/rel-touched", "zz/rel-small", "mm/main-three", "bb/main-two", "cc/main-two",
                "ff/unknown-big", "gg/unknown-small"]   # unknown-release API-touchers rank below every unreleased_main one

    def test_order_rules(self):
        ranked = pa.rank_candidates(ranking_fixture(), CRIT)
        assert [r["product"] for r in ranked] == self.EXPECTED
        assert [r["rank"] for r in ranked] == [1, 2, 3, 4, 5, 6, 7]
        assert {c["product"] for c in pa.classify_all(ranking_fixture(), CRIT) if not c["candidate"]} == {"ee/covered", "dd/propagated"}

    def test_input_order_is_irrelevant(self):
        base = pa.dumps(pa.build_candidates_report(ranking_fixture(), CRIT))
        for perm in itertools.islice(itertools.permutations(ranking_fixture()), 0, 5040, 211):
            assert pa.dumps(pa.build_candidates_report(list(perm), CRIT)) == base
        shuffled = ranking_fixture()
        random.Random(7).shuffle(shuffled)
        assert pa.dumps(pa.build_candidates_report(shuffled, CRIT)) == base

    def test_gap_units_count_desc_then_lexicographic(self):
        a = [mk_analysis(f"{n}/p", release_state="unreleased_main", touched=True,
                         units=[mk_unit_a(f"U{i}") for i in range(c)]) for n, c in (("b", 1), ("a", 1), ("c", 4), ("d", 2))]
        assert [r["product"] for r in pa.rank_candidates(a, CRIT)] == ["c/p", "d/p", "a/p", "b/p"]


class TestUnknownReleaseState:
    def test_unknown_release_with_api_touch_is_a_candidate_with_reason(self):
        ev = pa.evaluate_candidate(mk_analysis("f/a", release_state="unknown", touched=True), CRIT)
        assert ev["candidate"] is True and ev["release_triggered"] is False
        assert "release_evidence: unknown" in ev["reasons"]
        assert ev["criteria"]["1_drift_release"]["evidence"]["release_evidence"] == "unknown"
        assert ev["criteria"]["1_drift_release"]["evidence"]["trigger"] == "main_api_touched"
        known = pa.evaluate_candidate(mk_analysis("f/a", release_state="unreleased_main", touched=True), CRIT)
        assert "release_evidence: unknown" not in known["reasons"]

    def test_unknown_without_api_touch_is_still_no_signal(self):
        assert pa.evaluate_candidate(mk_analysis("f/a", release_state="unknown", touched=False), CRIT)["classification"] == "NO_DRIFT_SIGNAL"
        assert pa.evaluate_candidate(mk_analysis("f/a", release_state="unknown", touched=None), CRIT)["classification"] == "NO_DRIFT_SIGNAL"

    def test_default_ranking_places_unknown_below_unreleased_main_regardless_of_gap_count(self):
        many = [mk_unit_a(f"U{i}") for i in range(6)]
        a = [mk_analysis("aa/unknown", release_state="unknown", touched=True, units=many),
             mk_analysis("zz/main", release_state="unreleased_main", touched=True, units=[mk_unit_a("U1")]),
             mk_analysis("mm/release", new_release=True, release_state="unknown", touched=False)]
        assert [r["product"] for r in pa.rank_candidates(a, CRIT)] == ["mm/release", "zz/main", "aa/unknown"]

    def test_ranking_is_part_of_the_criteria(self):
        flipped = copy.deepcopy(CRIT)
        flipped["ranking"]["release_state_order"] = ["unknown", "unreleased_main"]
        a = [mk_analysis("aa/main", release_state="unreleased_main", touched=True),
             mk_analysis("zz/unknown", release_state="unknown", touched=True)]
        assert [r["product"] for r in pa.rank_candidates(a, CRIT)] == ["aa/main", "zz/unknown"]
        assert [r["product"] for r in pa.rank_candidates(a, flipped)] == ["zz/unknown", "aa/main"]
        gaps_first = copy.deepcopy(CRIT)
        gaps_first["ranking"]["order"] = ["release_triggered", "api_touched", "gap_units", "release_state", "product"]
        b = [mk_analysis("aa/main", release_state="unreleased_main", touched=True),
             mk_analysis("zz/unknown", release_state="unknown", touched=True, units=[mk_unit_a("U1"), mk_unit_a("U2")])]
        assert [r["product"] for r in pa.rank_candidates(b, CRIT)] == ["aa/main", "zz/unknown"]
        assert [r["product"] for r in pa.rank_candidates(b, gaps_first)] == ["zz/unknown", "aa/main"]

    def test_defaults_and_validator(self):
        assert CRIT["drift"]["main_release_states"] == ["unreleased_main", "unknown"]
        assert CRIT["ranking"] == {"order": ["release_triggered", "api_touched", "release_state", "gap_units", "product"],
                                   "release_state_order": ["unreleased_main", "unknown"]}
        assert CRIT["content_gap"]["max_coverage_ratio"] == 0.5
        bad = copy.deepcopy(CRIT)
        bad["ranking"]["order"] = ["product", "product", "gap_units", "api_touched", "release_state"]
        assert any("permutation" in e for e in pa.validate_criteria(bad))

    def test_unlisted_state_ranks_last(self):
        crit = copy.deepcopy(CRIT)
        crit["ranking"]["release_state_order"] = ["unreleased_main"]
        a = [mk_analysis("aa/unknown", release_state="unknown", touched=True),
             mk_analysis("zz/main", release_state="unreleased_main", touched=True)]
        assert [r["product"] for r in pa.rank_candidates(a, crit)] == ["zz/main", "aa/unknown"]


# ═══ content-gap rule: coverage over NEW public types ════════════════════════════════════════════

SHAPES = {   # three qualifier shapes: dotted package, PascalCase namespace, source-file path
    "dotted": lambda n: f"org.acme.widgets::Widget{chr(65 + n)}Node",
    "namespace": lambda n: f"Acme.Widgets::Widget{chr(65 + n)}Node",
    "filepath": lambda n: f"acme/widgets/w.py::Widget{chr(65 + n)}Node",
}


def type_unit(shape, count=18, *, members=0, formats=(), internal=()):
    syms = [SHAPES[shape](i) for i in range(count)]
    for j in range(members):
        syms.append(f"{SHAPES[shape](0)}.method{j}X")
    return {"id": "CU-GAP", "symbols": syms, "formats": list(formats), "internal_symbols": list(internal)}


def names_page(root, surface, names, rel="p.md"):
    put(root, surface, "f", "p", rel, page("Types: " + ", ".join(f"`{n}`" for n in names)))


class TestGapRule:
    @pytest.mark.parametrize("shape", sorted(SHAPES))
    @pytest.mark.parametrize("present,gap", [(0, True), (1, True), (8, True), (9, False), (10, False), (18, False)])
    def test_share_of_new_types_decides_both_sides_of_the_threshold(self, tmp_path, shape, present, gap):
        u = type_unit(shape)
        names_page(tmp_path, "docs", [f"Widget{chr(65 + i)}Node" for i in range(present)] or ["Unrelated"])
        r = scan_one(u, tmp_path, "f", "p")
        assert r["coverage"]["basis"] == "new_types" and len(r["coverage"]["new_symbols"]) == 18
        assert len(r["coverage"]["present_symbols"]) == present
        assert r["coverage"]["ratio"] == round(present / 18, 6)
        assert r["content_gap"] is gap                       # 9/18 = 0.5 is covered (gap iff ratio < 0.5)

    def test_threshold_is_configurable(self, tmp_path):
        u = type_unit("dotted")
        names_page(tmp_path, "docs", [f"Widget{chr(65 + i)}Node" for i in range(10)])
        assert scan_one(u, tmp_path, "f", "p")["content_gap"] is False
        strict = copy.deepcopy(CRIT)
        strict["content_gap"]["max_coverage_ratio"] = 0.6
        assert scan_one(u, tmp_path, "f", "p", strict)["content_gap"] is True      # 10/18 = 0.556 < 0.6
        lax = copy.deepcopy(CRIT)
        lax["content_gap"]["max_coverage_ratio"] = 0.05
        names_page(tmp_path, "docs", ["WidgetANode"])
        assert scan_one(u, tmp_path, "f", "p", lax)["content_gap"] is False        # 1/18 = 0.056 >= 0.05

    def test_surfaces_union_and_reference_does_not_count(self, tmp_path):
        u = type_unit("namespace")
        names_page(tmp_path, "docs", [f"Widget{chr(65 + i)}Node" for i in range(0, 5)])
        names_page(tmp_path, "kb", [f"Widget{chr(65 + i)}Node" for i in range(5, 10)])
        names_page(tmp_path, "reference", [f"Widget{chr(65 + i)}Node" for i in range(18)])
        r = scan_one(u, tmp_path, "f", "p")
        assert len(r["coverage"]["present_symbols"]) == 10 and r["content_gap"] is False   # docs + kb union
        assert sorted(r["coverage"]["by_surface"]) == sorted(pa.SURFACES)
        assert len(r["coverage"]["by_surface"]["docs"]) == 5 and len(r["coverage"]["by_surface"]["kb"]) == 5
        assert r["coverage"]["surfaces_carrying"] == ["docs", "kb", "reference"]
        only = copy.deepcopy(CRIT)
        only["content_gap"]["gap_surfaces"] = ["docs"]
        assert scan_one(u, tmp_path, "f", "p", only)["content_gap"] is True                 # 5/18

    def test_members_formats_and_an_existing_shared_name_do_not_cover_new_types(self, tmp_path):
        u = type_unit("dotted", members=20, formats=["HTML", "DocX"])
        names_page(tmp_path, "docs", ["HTML", "DocX", "WidgetANode"]
                   + [f"WidgetANode.method{j}X" for j in range(20)])
        r = scan_one(u, tmp_path, "f", "p")
        assert r["content_gap"] is True and r["coverage"]["ratio"] == round(1 / 18, 6)
        assert r["coverage"]["member_total"] == 22 and r["coverage"]["member_present"] >= 20
        assert r["coverage"]["member_ratio"] > 0.9              # secondary ratio is reported, never decisive

    def test_internal_new_types_are_not_the_basis(self, tmp_path):
        syms = [SHAPES["dotted"](i) for i in range(4)]
        u = {"id": "CU-I", "symbols": syms, "formats": [], "internal_symbols": syms[2:]}
        names_page(tmp_path, "docs", ["WidgetANode"])
        r = scan_one(u, tmp_path, "f", "p")
        assert len(r["coverage"]["new_symbols"]) == 2 and r["coverage"]["ratio"] == 0.5 and r["content_gap"] is False

    @pytest.mark.parametrize("shape", sorted(SHAPES))
    def test_unit_without_new_types_falls_back_to_all_new_symbols(self, tmp_path, shape):
        owner = SHAPES[shape](0)
        consts = [f"{owner}.MODE_{c}" for c in "ABCD"]
        u = {"id": "CU-C", "symbols": consts, "formats": [], "internal_symbols": []}
        names_page(tmp_path, "docs", ["WidgetANode", "MODE_A"])
        r = scan_one(u, tmp_path, "f", "p")
        assert r["coverage"]["basis"] == "all_new_symbols" and len(r["coverage"]["new_symbols"]) == 4
        assert r["coverage"]["present_symbols"] == ["WidgetANode.MODE_A"] and r["content_gap"] is True   # 1/4
        names_page(tmp_path, "docs", ["WidgetANode", "MODE_A", "MODE_B"])
        assert scan_one(u, tmp_path, "f", "p")["content_gap"] is False                                    # 2/4 = 0.5
        u2 = {"id": "CU-M", "symbols": [f"{owner}.callAlpha", f"{owner}.callBeta"], "formats": [], "internal_symbols": []}
        r2 = scan_one(u2, tmp_path, "f", "p")
        assert r2["coverage"]["basis"] == "all_new_symbols" and r2["content_gap"] is True

    def test_gt2_file_hint_is_its_own_basis(self, tmp_path):
        hint = {"id": "FH-1", "symbols": ["csv_reader"], "terms": [{"term": "csv_reader", "requires": None}]}
        r = scan_one(hint, tmp_path, "f", "p")
        assert r["coverage"]["basis"] == "new_types" and r["content_gap"] is True


# ═══ CLI ═════════════════════════════════════════════════════════════════════════════════════════

def delta_gt1():
    return {"ground_truth_tier": "GT-1", "added_types": [
        {"type": "org.acme.render.RenderOptions", "members": 2, "member_list": ["public int tiles();"], "is_enum": False}],
        "removed_types": [], "changed_types": {}}


def delta_gt2(api_files, platform="python"):
    return {"ground_truth_tier": "GT-2", "platform": platform, "known_platform": True, "changed_files": sorted(api_files),
            "added_source_files": sorted(api_files), "api_path_files": sorted(api_files), "source_files": sorted(api_files),
            "api_surface_touched": bool(api_files)}


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    products = [{"family": f, "platform": p, "active": True} for f, p in
                (("fama", "java"), ("famb", "python"), ("famc", "net"), ("famd", "python"))]
    products.append({"family": "famz", "platform": "java", "active": False})
    (root / "data" / "products.json").write_text(json.dumps(products), encoding="utf-8")
    (root / "data" / "package_registry.json").write_text(json.dumps({
        "fama": {"java": {"registry_type": "maven", "candidate": {"version": "2.0.0", "repo_sha": "1" * 40},
                          "verification": {"published": True}}}}), encoding="utf-8")
    write_model(root / "knowledge", "fama", "java", "a" * 40, "1.0.0")
    write_model(root / "knowledge", "famb", "python", "a" * 40, "1.0.0")
    write_model(root / "knowledge", "famc", "net", "a" * 40, "1.0.0")
    write_model(root / "knowledge", "famd", "python", "a" * 40, "1.0.0")
    fx = tmp_path / "fx"
    fx.mkdir()
    head = "b" * 40

    def fixture(name, **body):
        (fx / f"{name}.json").write_text(json.dumps({"head_ref": head, "base_ref": "a" * 40, **body}), encoding="utf-8")

    fixture("fama__java", adapter_delta=delta_gt1())                                    # new release + units
    fixture("famb__python", adapter_delta=delta_gt2(["src/acme/csv_reader.py"]))        # no registry => release `unknown`, API touched
    fixture("famc__net", adapter_delta=delta_gt2([], "net"), reachable=True)
    fixture("famd__python", adapter_delta=delta_gt2(["src/acme/x_mod.py"]), reachable=False)
    put(root / "content", "docs", "famb", "python", "a.md", page("nothing"))
    return {"root": root, "fx": fx, "out": tmp_path / "out", "tmp": tmp_path}


def run_cli(*argv):
    buf = io.StringIO()
    rc = cli.main(list(argv), out=buf)
    return rc, buf.getvalue()


class TestCli:
    def analyze_args(self, w, *extra):
        return ["analyze", "--repo-root", str(w["root"]), "--offline-fixtures", str(w["fx"]), "--out-dir", str(w["out"]),
                "--now", "2026-10-07T00:00:00Z", *extra]

    def test_offline_analyze_then_rank(self, world):
        rc, out = run_cli(*self.analyze_args(world))
        assert rc == 0 and "OK=3" in out and "ORPHANED_BASELINE=1" in out
        files = sorted(p.name for p in world["out"].glob("*.json"))
        assert files == ["fama__java.json", "famb__python.json", "famc__net.json", "famd__python.json"]  # inactive skipped
        a = json.loads((world["out"] / "fama__java.json").read_text(encoding="utf-8"))
        assert a["release"]["new_release"] is True and a["release"]["release_state"] == "unreleased_main"
        rc, out = run_cli("rank", "--repo-root", str(world["root"]), "--analysis-dir", str(world["out"]),
                          "--json-out", str(world["tmp"] / "c.json"), "--md-out", str(world["tmp"] / "c.md"))
        assert rc == 0
        rep = json.loads((world["tmp"] / "c.json").read_text(encoding="utf-8"))
        # release-triggered first; the unknown-release API-touching product is a candidate ranked below it
        assert [c["product"] for c in rep["candidates"]] == ["fama/java", "famb/python"]
        assert "release_evidence: unknown" in rep["candidates"][1]["reasons"]
        assert "release_evidence: unknown" not in rep["candidates"][0]["reasons"]
        cls = {e["product"]: e["classification"] for e in rep["excluded"]}
        assert cls == {"famc/net": "NO_DRIFT_SIGNAL", "famd/python": "ORPHANED_BASELINE"}
        assert rep["summary"]["total"] == 4
        md = (world["tmp"] / "c.md").read_text(encoding="utf-8")
        assert "fama/java" in md and "ORPHANED_BASELINE" in md

    def test_rank_rerun_is_byte_identical_and_analyze_is_stable(self, world):
        run_cli(*self.analyze_args(world))
        first = {p.name: p.read_bytes() for p in world["out"].glob("*.json")}
        run_cli(*self.analyze_args(world))
        assert {p.name: p.read_bytes() for p in world["out"].glob("*.json")} == first
        outs = []
        for i in range(2):
            j, md = world["tmp"] / f"c{i}.json", world["tmp"] / f"c{i}.md"
            run_cli("rank", "--repo-root", str(world["root"]), "--analysis-dir", str(world["out"]),
                    "--json-out", str(j), "--md-out", str(md))
            outs.append((j.read_bytes(), md.read_bytes()))
        assert outs[0] == outs[1]
        assert b"\r\n" not in outs[0][0] and b"\r\n" not in outs[0][1]

    def test_wall_clock_only_under_volatile(self, world):
        run_cli(*self.analyze_args(world))
        a = pa.canonical_for_compare(json.loads((world["out"] / "fama__java.json").read_text(encoding="utf-8")))
        run_cli("analyze", "--repo-root", str(world["root"]), "--offline-fixtures", str(world["fx"]),
                "--out-dir", str(world["out"]), "--now", "2031-05-05T05:05:05Z")
        b = pa.canonical_for_compare(json.loads((world["out"] / "fama__java.json").read_text(encoding="utf-8")))
        assert a == b

    def test_never_writes_the_state_file(self, world):
        state = world["root"] / "data" / "content_propagation_state.json"
        run_cli(*self.analyze_args(world))
        assert not state.exists()
        state.write_text(json.dumps({"schema_version": 1, "products": {}}), encoding="utf-8")
        before = state.read_bytes()
        run_cli(*self.analyze_args(world))
        assert state.read_bytes() == before and not Path(str(state) + ".lock").exists()

    def test_missing_fixture_is_an_error_record_not_a_crash(self, world):
        (world["fx"] / "famc__net.json").unlink()
        rc, out = run_cli(*self.analyze_args(world))
        assert rc == 0 and "ERROR=1" in out
        rec = json.loads((world["out"] / "famc__net.json").read_text(encoding="utf-8"))
        assert rec["status"] == "ERROR" and "fixture" in rec["error"]

    def test_products_filter_and_bad_arguments(self, world):
        rc, _ = run_cli(*self.analyze_args(world, "--products", "fama/java"))
        assert rc == 0 and [p.name for p in world["out"].glob("*.json")] == ["fama__java.json"]
        rc, _ = run_cli(*self.analyze_args(world, "--products", "bad"))
        assert rc == 2
        bad = world["tmp"] / "crit.yaml"
        bad.write_text("nonsense: 1\n", encoding="utf-8")
        rc, _ = run_cli(*self.analyze_args(world, "--criteria", str(bad)))
        assert rc == 2
        rc, _ = run_cli("rank", "--analysis-dir", str(world["tmp"] / "nodir"), "--json-out", "x", "--md-out", "y")
        assert rc == 2

    def test_bundles_option_single_product_only(self, world):
        write_bundle(world["tmp"] / "bo", JAVA_B_OLD, "1" * 40, "1.0.0")
        write_bundle(world["tmp"] / "bn", mutate(JAVA_B_OLD, "java"), "2" * 40, "2.0.0")
        args = ["analyze", "--repo-root", str(world["root"]), "--out-dir", str(world["out"]),
                "--bundles", str(world["tmp"] / "bo"), str(world["tmp"] / "bn")]
        rc, _ = run_cli(*args)                       # four products without --products
        assert rc == 2
        rc, out = run_cli(*args, "--products", "fama/java")
        assert rc == 0 and "OK=1" in out
        a = json.loads((world["out"] / "fama__java.json").read_text(encoding="utf-8"))
        assert a["method"] == "bundles" and a["ground_truth_tier"] == "KNOWLEDGE"

    def test_max_repos_bounds_real_clones_and_defers_the_rest(self, world):
        cache = world["tmp"] / "cache"
        cache.mkdir()
        origin, shas = py_origin(world["tmp"])
        for fam in ("famb", "famd"):
            shallow_clone(origin, cache / f"aspose_{fam}_python")
            write_model(world["root"] / "knowledge", fam, "python", shas[0], "1.0.0")
        before = os.environ.get("ASPOSE_CLONE_CACHE")
        rc, out = run_cli("analyze", "--repo-root", str(world["root"]), "--out-dir", str(world["out"]),
                          "--clone-cache", str(cache), "--products", "famb/python", "famd/python", "--max-repos", "1",
                          "--now", "2026-10-07T00:00:00Z")
        assert rc == 0 and "DEFERRED=1" in out and "OK=1" in out
        assert os.environ.get("ASPOSE_CLONE_CACHE") == before          # the cache override never leaks
        first = json.loads((world["out"] / "famb__python.json").read_text(encoding="utf-8"))
        second = json.loads((world["out"] / "famd__python.json").read_text(encoding="utf-8"))
        assert first["status"] == "OK" and first["ground_truth_tier"] == "GT-2"
        assert {h["symbols"][0] for h in first["file_hints"]} == {"csv_reader", "parser"}
        assert second["status"] == "DEFERRED" and "max_repos" in second["error"]
        assert git(cache / "aspose_famb_python", "status", "--porcelain") == ""
        rep_args = ["rank", "--repo-root", str(world["root"]), "--analysis-dir", str(world["out"]),
                    "--json-out", str(world["tmp"] / "r.json"), "--md-out", str(world["tmp"] / "r.md")]
        run_cli(*rep_args)
        rep = json.loads((world["tmp"] / "r.json").read_text(encoding="utf-8"))
        assert {e["product"]: e["classification"] for e in rep["excluded"]}["famd/python"] == "DEFERRED"

    def test_criteria_file_is_used_by_rank(self, world):
        run_cli(*self.analyze_args(world))
        crit = world["tmp"] / "crit.yaml"
        crit.write_text("analysable:\n  tiers: [GT-2]\n", encoding="utf-8")
        run_cli("rank", "--repo-root", str(world["root"]), "--analysis-dir", str(world["out"]), "--criteria", str(crit),
                "--json-out", str(world["tmp"] / "c.json"), "--md-out", str(world["tmp"] / "c.md"))
        rep = json.loads((world["tmp"] / "c.json").read_text(encoding="utf-8"))
        assert [c["product"] for c in rep["candidates"]] == ["famb/python"]   # GT-2 only: the GT-1 product drops out
        assert {e["product"]: e["classification"] for e in rep["excluded"]}["fama/java"] == "NOT_ANALYSABLE"
        assert rep["criteria_sha256"] == pa.criteria_digest(pa.load_criteria(crit))


# ═══ G-1 generality ══════════════════════════════════════════════════════════════════════════════

class TestGenerality:
    BANNED = re.compile(r"\b(java|python|typescript|javascript|csharp|cpp|golang|rust|pdf|docx|xlsx|pptx|markdown|"
                        r"cells|slides|imaging|barcode|ocr)\b", re.I)

    @pytest.mark.parametrize("rel", ["lib/propagation_analyzer.py", "commands/diagnostics/propagation_analyze.py"])
    def test_no_product_family_language_or_format_literals(self, rel):
        text = (Path(__file__).resolve().parents[1] / rel).read_text(encoding="utf-8")
        text = text.replace("aspose.org", "")          # the site hostnames in the path templates are site names
        hits = sorted({m.group(0).lower() for m in self.BANNED.finditer(text)})
        assert hits == [], f"G-1: product/language/format literal(s) in shipped code: {hits}"


# ═══ E0: frozen discovery criteria ═══════════════════════════════════════════════════════════════

class TestFrozenDiscoveryCriteria:
    """E0 froze config/discovery_criteria.yaml in its own commit before Wave E ever runs. This pins
    it to exactly DEFAULT_CRITERIA, and to a frozen schema shape, so a later edit to either is a
    visible, deliberate diff (never a silent re-tune in the same commit as a run)."""

    PATH = Path(__file__).resolve().parents[1] / "config" / "discovery_criteria.yaml"

    def test_frozen_file_exists(self):
        assert self.PATH.is_file(), "config/discovery_criteria.yaml must be frozen before Wave E (card E0)"

    def test_frozen_file_round_trips_to_default_criteria(self):
        assert pa.load_criteria(self.PATH) == pa.DEFAULT_CRITERIA

    def test_frozen_file_validates_cleanly(self):
        # load_criteria raises CriteriaError on any schema violation -- reaching this line is the assertion
        pa.load_criteria(self.PATH)

    def test_frozen_file_has_a_stable_digest(self):
        d1 = pa.criteria_digest(pa.load_criteria(self.PATH))
        d2 = pa.criteria_digest(pa.load_criteria(self.PATH))
        assert d1 == d2
        assert len(d1) == 64  # sha256 hex
