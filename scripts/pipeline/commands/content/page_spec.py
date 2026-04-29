"""Deterministic page specification — load site plans and reconcile with disk.

Bridges the gap between site_planner.py (YAML plan output) and batch_reference.py
(page generation). Provides:
- PageSpec / SectionPlan / SitePlan dataclasses
- load_plan() to deserialize site_plan.yaml
- reconcile() to compare planned pages vs actual pages on disk
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_ROOT = Path(__file__).resolve().parents[4]
_ROOT = _DEFAULT_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _ROOT
    _ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_ROOT


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PageSpec:
    """Single page entry from a site plan."""

    slug: str
    path: str
    weight: int = 0
    mandatory: bool = False
    page_class: str = "generated"
    note: str = ""

    # Section-specific optional fields
    layout: str = ""
    type: str = ""
    page_role: str = ""
    blog_role: str = ""
    source: str = ""
    cluster: str = ""
    claim_count: int = 0
    api_method_count: int = 0
    candidate_class_count: int = 0
    license_source: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PageSpec:
        """Create PageSpec from a plan YAML dict, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


@dataclass
class SectionPlan:
    """A section within a site plan (products, blog, docs, kb, reference)."""

    name: str
    page_count: int = 0
    pages: list[PageSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> SectionPlan:
        raw_pages = d.get("pages", [])
        pages = [PageSpec.from_dict(p) for p in raw_pages]
        return cls(
            name=name,
            page_count=d.get("page_count", len(pages)),
            pages=pages,
        )


@dataclass
class SitePlan:
    """Full site plan loaded from site_plan.yaml."""

    family: str
    platform: str
    schema_version: int = 1
    plan_version: int = 1
    repo_sha: str = ""
    knowledge_version: str = ""
    launch_tier: str = ""
    generated_at: str = ""
    sections: dict[str, SectionPlan] = field(default_factory=dict)

    @property
    def all_pages(self) -> list[PageSpec]:
        """Flatten all pages across all sections."""
        result = []
        for section in self.sections.values():
            result.extend(section.pages)
        return result

    @property
    def total_page_count(self) -> int:
        return sum(s.page_count for s in self.sections.values())


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_plan(path: str | Path) -> SitePlan:
    """Load a site plan from a YAML file.

    Args:
        path: Path to site_plan.yaml

    Returns:
        SitePlan with all sections and pages parsed.

    Raises:
        FileNotFoundError: if path doesn't exist
        ValueError: if YAML structure is invalid
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Plan file not found: {p}")

    text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    if not isinstance(data, dict) or "plan" not in data:
        raise ValueError(f"Invalid plan file: missing top-level 'plan' key in {p}")

    plan_data = data["plan"]

    sections = {}
    raw_sections = plan_data.get("sections", {})
    for section_name, section_data in raw_sections.items():
        if isinstance(section_data, dict):
            sections[section_name] = SectionPlan.from_dict(section_name, section_data)

    return SitePlan(
        family=plan_data.get("family", ""),
        platform=plan_data.get("platform", ""),
        schema_version=plan_data.get("schema_version", 1),
        plan_version=plan_data.get("plan_version", 1),
        repo_sha=plan_data.get("repo_sha", ""),
        knowledge_version=plan_data.get("knowledge_version", ""),
        launch_tier=plan_data.get("launch_tier", ""),
        generated_at=plan_data.get("generated_at", ""),
        sections=sections,
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

@dataclass
class ReconcileResult:
    """Result of comparing a site plan against actual files on disk."""

    plan_path: str
    family: str
    platform: str
    missing: list[PageSpec] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    matched: list[PageSpec] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.missing) == 0 and len(self.extra) == 0

    def summary(self) -> str:
        lines = [
            f"RECONCILE — {self.family}/{self.platform}",
            f"  Plan: {self.plan_path}",
            f"  Matched: {len(self.matched)}",
            f"  Missing: {len(self.missing)}",
            f"  Extra:   {len(self.extra)}",
        ]
        if self.missing:
            lines.append("  Missing pages:")
            for p in self.missing:
                tag = " [mandatory]" if p.mandatory else ""
                lines.append(f"    - {p.path}{tag}")
        if self.extra:
            lines.append("  Extra pages (on disk but not in plan):")
            for path in self.extra[:20]:
                lines.append(f"    - {path}")
            if len(self.extra) > 20:
                lines.append(f"    ... and {len(self.extra) - 20} more")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_path": self.plan_path,
            "family": self.family,
            "platform": self.platform,
            "matched_count": len(self.matched),
            "missing_count": len(self.missing),
            "extra_count": len(self.extra),
            "is_clean": self.is_clean,
            "missing": [{"path": p.path, "slug": p.slug, "mandatory": p.mandatory}
                        for p in self.missing],
            "extra": self.extra,
        }


def reconcile(
    plan: SitePlan,
    root: Path | None = None,
    sections: list[str] | None = None,
) -> ReconcileResult:
    """Compare a site plan against actual files on disk.

    Args:
        plan: Loaded SitePlan to check
        root: Repository root (defaults to _ROOT)
        sections: If provided, only reconcile these sections (e.g. ["reference", "docs"])

    Returns:
        ReconcileResult with missing, extra, and matched pages.
    """
    root = root or _ROOT

    # Collect planned pages (optionally filtered by section)
    planned_pages: list[PageSpec] = []
    for name, section in plan.sections.items():
        if sections and name not in sections:
            continue
        planned_pages.extend(section.pages)

    # Build set of planned paths (relative to root)
    planned_paths = {p.path for p in planned_pages}

    # Check which planned pages exist on disk
    missing = []
    matched = []
    for page in planned_pages:
        full_path = root / page.path
        if full_path.exists():
            matched.append(page)
        else:
            missing.append(page)

    # Find extra files on disk not in the plan
    # Scan all content directories referenced by the plan's sections
    extra = []
    scanned_dirs: set[Path] = set()
    for page in planned_pages:
        content_dir = (root / page.path).parent
        if content_dir in scanned_dirs:
            continue
        scanned_dirs.add(content_dir)
        if content_dir.exists():
            for md_file in content_dir.glob("*.md"):
                rel_path = str(md_file.relative_to(root)).replace("\\", "/")
                if rel_path not in planned_paths:
                    extra.append(rel_path)

    extra.sort()

    return ReconcileResult(
        plan_path=f"reports/plans/{plan.family}/{plan.platform}/site_plan.yaml",
        family=plan.family,
        platform=plan.platform,
        missing=missing,
        extra=extra,
        matched=matched,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile site plan against actual content files on disk"
    )
    parser.add_argument("plan", help="Path to site_plan.yaml")
    parser.add_argument("--sections", help="Comma-separated section names to check (default: all)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if any mandatory pages are missing")

    args = parser.parse_args()

    plan = load_plan(args.plan)
    section_filter = args.sections.split(",") if args.sections else None
    result = reconcile(plan, sections=section_filter)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.summary())

    if args.strict:
        mandatory_missing = [p for p in result.missing if p.mandatory]
        if mandatory_missing:
            print(f"\nERROR: {len(mandatory_missing)} mandatory page(s) missing", file=sys.stderr)
            sys.exit(1)

    if not result.is_clean:
        sys.exit(2)


if __name__ == "__main__":
    main()
