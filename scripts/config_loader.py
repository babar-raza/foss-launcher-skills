"""Shared configuration loader for foss-launcher-skills.

Provides content repo path resolution used by all pipeline scripts.
"""
import os
from pathlib import Path

import yaml


def _find_config() -> Path:
    """Walk up from CWD or script dir to find config.yaml."""
    for start in (Path.cwd(), Path(__file__).resolve().parent.parent):
        candidate = start / "config.yaml"
        if candidate.is_file():
            return candidate
    return Path("config.yaml")


def load_config() -> dict:
    """Load and return the parsed config.yaml."""
    path = _find_config()
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_content_repo() -> Path:
    """Resolve the content repo root path.

    Resolution order:
      1. $CONTENT_REPO_PATH environment variable
      2. content_repo field in config.yaml
      3. Current working directory (fallback)
    """
    env_path = os.environ.get("CONTENT_REPO_PATH")
    if env_path and Path(env_path).is_dir():
        return Path(env_path).resolve()

    config = load_config()
    repo = config.get("content_repo", "")
    if repo and Path(repo).is_dir():
        return Path(repo).resolve()

    return Path.cwd()


def resolve_content_path(site_type: str, family: str, platform: str = "") -> Path:
    """Resolve the full content path for a given site type and product.

    Args:
        site_type: One of docs, blog, kb, products, reference.
        family: Product family (e.g. "3d", "cells").
        platform: Platform (e.g. "python", "net"). Not used for products.

    Returns:
        Absolute path to the content directory.
    """
    config = load_config()
    sites = config.get("sites", {})
    site = sites.get(site_type, {})
    template = site.get("content_path", "")
    if not template:
        raise ValueError(f"Unknown site type: {site_type}")

    path_str = template.replace("{family}", family).replace("{platform}", platform)
    return resolve_content_repo() / path_str


def resolve_knowledge_path(family: str, platform: str) -> Path:
    """Resolve the knowledge directory for a product."""
    config = load_config()
    template = config.get("knowledge_path", "knowledge/{family}/{platform}/")
    path_str = template.replace("{family}", family).replace("{platform}", platform)
    return Path(path_str)


def resolve_intake_config() -> Path:
    """Resolve path to configs/intake_config.yaml."""
    config = load_config()
    path = config.get("intake_config", "configs/intake_config.yaml")
    return Path(path)


def resolve_families_config() -> Path:
    """Resolve path to configs/families.yaml."""
    config = load_config()
    path = config.get("families_config", "configs/families.yaml")
    return Path(path)


def golden_corpus_config() -> dict:
    """Return golden corpus settings from config."""
    config = load_config()
    return config.get("golden_corpus", {
        "sample_count": 3,
        "min_words": 200,
        "profile_dir": "_corpus",
    })


def resolve_evidence_path(family: str, platform: str) -> Path:
    """Resolve the evidence directory for a product."""
    config = load_config()
    template = config.get("evidence_path", "evidence/{family}/{platform}/")
    path_str = template.replace("{family}", family).replace("{platform}", platform)
    return Path(path_str)


def resolve_golden_dir() -> Path:
    """Resolve path to the golden corpus directory.

    Resolution order:
      1. $GOLDEN_DIR environment variable
      2. golden_dir field in config.yaml
      3. golden/ relative to project root (fallback)
    """
    env_path = os.environ.get("GOLDEN_DIR")
    if env_path and Path(env_path).is_dir():
        return Path(env_path).resolve()

    config = load_config()
    golden = config.get("golden_dir", "golden/")
    golden_path = Path(golden)
    if golden_path.is_dir():
        return golden_path.resolve()

    # Try relative to config file location
    config_path = _find_config()
    candidate = config_path.parent / golden
    if candidate.is_dir():
        return candidate.resolve()

    return Path("golden/").resolve()
