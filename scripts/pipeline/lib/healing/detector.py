"""detector.py — Healing detection functions.

Each detector scans for a specific issue type and returns a list of
HealingFinding dataclass instances. Findings are consumed by the
classifier to determine remediation strategy.

Usage:
    from healing.detector import detect_missing_pages, HealingFinding
    findings = detect_missing_pages("font", "python",
                                     knowledge_root=Path("knowledge"),
                                     content_root=Path("content"))
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


class IssueType(str, Enum):
    MISSING_PAGE = "missing_page"
    STALE_PAGE = "stale_page"
    HIERARCHY_DRIFT = "hierarchy_drift"
    SILENT_OMISSION = "silent_omission"
    GRADE_REGRESSION = "grade_regression"
    METADATA_CORRUPTION = "metadata_corruption"
    NAMING_DRIFT = "naming_drift"
    FORMAT_CONTRADICTION = "format_contradiction"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class HealingFinding:
    issue_type: IssueType
    severity: Severity
    entity: str
    detail: str
    file_path: str = ""
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detector implementations
# ---------------------------------------------------------------------------

def detect_missing_pages(
    family: str, platform: str, *,
    knowledge_root: Path, content_root: Path,
) -> list[HealingFinding]:
    """Find api_surface entries with no corresponding page on disk."""
    from denominator_reconciler import reconcile

    report = reconcile(family, platform,
                       knowledge_root=knowledge_root,
                       content_root=content_root)
    findings = []
    for name in report.get("missing_pages", []):
        findings.append(HealingFinding(
            issue_type=IssueType.MISSING_PAGE,
            severity=Severity.CRITICAL,
            entity=name,
            detail=f"Class {name} in api_surface but no page on disk",
        ))
    return findings


def detect_stale_pages(
    family: str, platform: str, *,
    knowledge_root: Path, content_root: Path,
) -> list[HealingFinding]:
    """Find pages where evidence.model_sha != current model.yaml repo_sha."""
    import yaml

    model_path = knowledge_root / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return []
    try:
        model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []

    current_sha = model.get("repo_sha", "")
    if not current_sha:
        return []

    content_dir = content_root / "reference.aspose.org" / "en" / family / platform
    if not content_dir.exists():
        return []

    findings = []
    for md_file in sorted(content_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        page_sha = _extract_frontmatter_value(text, "model_sha")
        if page_sha and page_sha != current_sha:
            findings.append(HealingFinding(
                issue_type=IssueType.STALE_PAGE,
                severity=Severity.HIGH,
                entity=md_file.stem,
                detail=f"page sha={page_sha} != model sha={current_sha}",
                file_path=str(md_file),
            ))
    return findings


def detect_hierarchy_drift(
    family: str, platform: str, *,
    content_root: Path,
) -> list[HealingFinding]:
    """Find missing _index.md files in content directories."""
    findings = []
    sites = ["reference.aspose.org", "docs.aspose.org", "kb.aspose.org"]

    for site in sites:
        family_dir = content_root / site / "en" / family
        if not family_dir.exists():
            continue
        platform_dir = family_dir / platform
        if platform_dir.exists() and not (platform_dir / "_index.md").exists():
            findings.append(HealingFinding(
                issue_type=IssueType.HIERARCHY_DRIFT,
                severity=Severity.HIGH,
                entity=f"{site}/{family}/{platform}",
                detail=f"Missing _index.md in {site}/en/{family}/{platform}/",
                file_path=str(platform_dir),
            ))
        if not (family_dir / "_index.md").exists():
            findings.append(HealingFinding(
                issue_type=IssueType.HIERARCHY_DRIFT,
                severity=Severity.HIGH,
                entity=f"{site}/{family}",
                detail=f"Missing _index.md in {site}/en/{family}/",
                file_path=str(family_dir),
            ))
    return findings


def detect_metadata_corruption(
    family: str, platform: str, *,
    content_root: Path,
) -> list[HealingFinding]:
    """Find pages with missing or malformed frontmatter/evidence block."""
    content_dir = content_root / "reference.aspose.org" / "en" / family / platform
    if not content_dir.exists():
        return []

    findings = []
    for md_file in sorted(content_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            findings.append(HealingFinding(
                issue_type=IssueType.METADATA_CORRUPTION,
                severity=Severity.HIGH,
                entity=md_file.stem,
                detail="File unreadable",
                file_path=str(md_file),
            ))
            continue

        if not text.startswith("---"):
            findings.append(HealingFinding(
                issue_type=IssueType.METADATA_CORRUPTION,
                severity=Severity.HIGH,
                entity=md_file.stem,
                detail="Missing frontmatter delimiters",
                file_path=str(md_file),
            ))
            continue

        end = text.find("\n---", 3)
        if end == -1:
            findings.append(HealingFinding(
                issue_type=IssueType.METADATA_CORRUPTION,
                severity=Severity.HIGH,
                entity=md_file.stem,
                detail="Unclosed frontmatter",
                file_path=str(md_file),
            ))
            continue

        frontmatter = text[3:end]
        has_evidence = any(
            line.startswith("evidence:") or line.strip() == "evidence:"
            for line in frontmatter.splitlines()
        )
        if not has_evidence:
            findings.append(HealingFinding(
                issue_type=IssueType.METADATA_CORRUPTION,
                severity=Severity.HIGH,
                entity=md_file.stem,
                detail="Missing evidence block in frontmatter",
                file_path=str(md_file),
            ))
    return findings


def detect_naming_drift(
    family: str, platform: str, *,
    knowledge_root: Path, content_root: Path,
) -> list[HealingFinding]:
    """Find pages whose filename doesn't match the sanitized class name."""
    _CMD_CONTENT = Path(__file__).resolve().parent.parent.parent / "commands" / "content"
    if str(_CMD_CONTENT) not in sys.path:
        sys.path.insert(0, str(_CMD_CONTENT))
    import batch_reference as br

    api_path = knowledge_root / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        return []

    api_surface = json.loads(api_path.read_text(encoding="utf-8"))
    content_dir = content_root / "reference.aspose.org" / "en" / family / platform

    findings = []
    for entry in api_surface:
        name = entry.get("name", "")
        if not br._passes_platform_scope(entry, platform):
            continue
        sanitized = br._sanitize_slug(name)
        if sanitized != name and content_dir.exists():
            # Check if the file uses the original (unsanitized) name
            unsanitized_path = content_dir / f"{name}.md"
            sanitized_path = content_dir / f"{sanitized}.md"
            if unsanitized_path.exists() and not sanitized_path.exists():
                findings.append(HealingFinding(
                    issue_type=IssueType.NAMING_DRIFT,
                    severity=Severity.MEDIUM,
                    entity=name,
                    detail=f"Page uses unsanitized name '{name}.md', should be '{sanitized}.md'",
                    file_path=str(unsanitized_path),
                ))
    return findings


def detect_format_contradictions(
    family: str, platform: str, *,
    knowledge_root: Path, content_root: Path,
) -> list[HealingFinding]:
    """Find pages that claim format support contradicting formats.json."""
    formats_path = knowledge_root / family / platform / "merged" / "formats.json"
    if not formats_path.exists():
        return []

    try:
        formats_data = json.loads(formats_path.read_text(encoding="utf-8"))
        known_formats = {
            f.get("name", "").lower()
            for f in formats_data.get("formats", [])
        }
    except Exception:
        return []

    # This detector is a stub — full implementation requires parsing page
    # content for format claims and comparing against known_formats.
    # For now, returns empty (no contradictions detected without content parsing).
    return []


def detect_silent_omissions(
    family: str, platform: str, *,
    knowledge_root: Path, content_root: Path,
) -> list[HealingFinding]:
    """Find public classes filtered by scope rules that might be incorrectly excluded."""
    from denominator_reconciler import reconcile

    report = reconcile(family, platform,
                       knowledge_root=knowledge_root,
                       content_root=content_root)
    findings = []
    for entry in report.get("scope_filter_log", []):
        name = entry.get("name", "")
        reason = entry.get("reason", "")
        # Only flag entries that look like they might be public classes
        # (CamelCase names, not functions/helpers)
        if name and name[0].isupper() and "_" not in name:
            findings.append(HealingFinding(
                issue_type=IssueType.SILENT_OMISSION,
                severity=Severity.MEDIUM,
                entity=name,
                detail=f"Public-looking class filtered: {reason}",
            ))
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_frontmatter_value(text: str, key: str) -> str | None:
    """Extract a simple key: value from YAML frontmatter."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    for line in text[3:end].splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            val = stripped[len(key) + 1:].strip().strip("'\"")
            return val if val else None
    return None
