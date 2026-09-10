"""
Tests for commands/ops/enrich_products_cmake_targets.py (ST-054 TC-12,
governing plan §Q.3a).
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.enrich_products_cmake_targets as sut


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)


def _write_registry(tmp_path: Path, entries: dict) -> None:
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "package_registry.json").write_text(json.dumps(entries), encoding="utf-8")


def _write_products(tmp_path: Path, entries: list) -> None:
    (tmp_path / "data" / "products.json").write_text(json.dumps(entries), encoding="utf-8")


def _write_cmakelists(tmp_path: Path, family: str, platform: str, content: str) -> None:
    clone_dir = tmp_path / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    clone_dir.mkdir(parents=True, exist_ok=True)
    (clone_dir / "CMakeLists.txt").write_text(content, encoding="utf-8")


def test_enriches_unpublished_cpp_product_with_real_target(tmp_path):
    _write_registry(tmp_path, {
        "slides": {"cpp": {"registry_type": "nuget", "candidate": {"name": "aspose_slides_foss"},
                             "verification": {"published": False}}},
    })
    _write_products(tmp_path, [
        {"family": "slides", "platform": "cpp", "repo_name": "Aspose.Slides-FOSS-for-Cpp",
         "repo_url": "https://github.com/aspose-slides-foss/Aspose.Slides-FOSS-for-Cpp"},
    ])
    _write_cmakelists(tmp_path, "slides", "cpp", (
        "project(AsposeSlidesFoss LANGUAGES CXX)\n"
        "add_library(AsposeSlidesFoss STATIC ${SOURCES})\n"
        "add_library(AsposeSlidesFoss::AsposeSlidesFoss ALIAS AsposeSlidesFoss)\n"
    ))

    summary = sut.run_enrichment(dry_run=False)
    assert summary["targets_found"] == 1
    products = json.loads((tmp_path / "data" / "products.json").read_text(encoding="utf-8"))
    assert products[0]["cmake_target"] == "AsposeSlidesFoss::AsposeSlidesFoss"
    assert products[0]["cmake_project"] == "AsposeSlidesFoss"


def test_ignores_published_cpp_product(tmp_path):
    _write_registry(tmp_path, {
        "cells": {"cpp": {"registry_type": "nuget", "candidate": {"name": "Aspose.Cells.Cpp.FOSS"},
                            "verification": {"published": True}}},
    })
    _write_products(tmp_path, [
        {"family": "cells", "platform": "cpp", "repo_name": "Aspose.Cells-FOSS-for-Cpp",
         "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Cpp"},
    ])
    summary = sut.run_enrichment(dry_run=False)
    assert summary["targets_found"] == 0
    products = json.loads((tmp_path / "data" / "products.json").read_text(encoding="utf-8"))
    assert "cmake_target" not in products[0]


def test_ambiguous_cmakelists_writes_null_not_a_guess(tmp_path):
    _write_registry(tmp_path, {
        "pdf": {"cpp": {"registry_type": "nuget", "candidate": {"name": "Aspose_PDF_FOSS"},
                          "verification": {"published": False}}},
    })
    _write_products(tmp_path, [
        {"family": "pdf", "platform": "cpp", "repo_name": "Aspose.PDF-FOSS-for-Cpp",
         "repo_url": "https://github.com/aspose-pdf-foss/Aspose.PDF-FOSS-for-Cpp"},
    ])
    _write_cmakelists(tmp_path, "pdf", "cpp", (
        "project(Multi LANGUAGES CXX)\n"
        "add_library(FooImpl STATIC ${A})\n"
        "add_library(BarImpl STATIC ${B})\n"
    ))
    summary = sut.run_enrichment(dry_run=False)
    products = json.loads((tmp_path / "data" / "products.json").read_text(encoding="utf-8"))
    assert products[0]["cmake_target"] is None


def test_dry_run_does_not_write_products_json(tmp_path):
    _write_registry(tmp_path, {
        "slides": {"cpp": {"registry_type": "nuget", "candidate": {"name": "aspose_slides_foss"},
                             "verification": {"published": False}}},
    })
    _write_products(tmp_path, [
        {"family": "slides", "platform": "cpp", "repo_name": "Aspose.Slides-FOSS-for-Cpp",
         "repo_url": "https://github.com/aspose-slides-foss/Aspose.Slides-FOSS-for-Cpp"},
    ])
    _write_cmakelists(tmp_path, "slides", "cpp",
                       "project(X LANGUAGES CXX)\nadd_library(X STATIC ${A})\n")
    original = (tmp_path / "data" / "products.json").read_text(encoding="utf-8")
    summary = sut.run_enrichment(dry_run=True)
    assert summary["results"][0]["cmake_target"] == "X"
    assert (tmp_path / "data" / "products.json").read_text(encoding="utf-8") == original
