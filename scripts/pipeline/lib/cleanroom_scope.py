"""
TC-S96-004: Cleanroom Scope Resolver.

Maps any (family, platform, subdomain) target to content paths,
knowledge paths, and generation entry points.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

VALID_SUBDOMAINS = ["reference", "blog", "docs", "kb", "products"]

_SUBDOMAIN_GENERATORS = {
    "reference": {
        "type": "script",
        "command": "batch_reference.py {family} {platform} --rebuild-all --confirm-rebuild",
        "skill": "S-62",
    },
    "blog":     {"type": "agent", "skill": "S-57", "per": "slug"},
    "docs":     {"type": "agent", "skill": "S-56", "per": "slug"},
    "kb":       {"type": "agent", "skill": "S-58", "per": "slug"},
    "products": {"type": "agent", "skill": "S-61", "per": "platform"},
}

_CONTENT_ROOT_TEMPLATES = {
    "reference": "content/reference.aspose.org/en/{family}/{platform}",
    "blog":      "content/blog.aspose.org/{family}/{platform}",
    "docs":      "content/docs.aspose.org/en/{family}/{platform}",
    "kb":        "content/kb.aspose.org/en/{family}/{platform}",
    "products":  "content/products.aspose.org/en/{family}/{platform}",
}

_KNOWN_FAMILIES = {
    "cells", "words", "slides", "pdf", "email", "barcode", "ocr",
    "imaging", "html", "cad", "diagram", "zip", "font", "page", "pub",
    "tasks", "note", "gis", "finance", "3d", "omr", "formulas", "psd",
}


@dataclass
class ScopeManifest:
    family: str
    platform: Optional[str]
    subdomains: List[str]
    files: List[str]
    content_roots: Dict[str, str]
    knowledge_model_path: Optional[str]
    claims_path: Optional[str]
    api_surface_path: Optional[str]
    site_plan_path: Optional[str]
    generation_entry_points: Dict[str, dict]
    _errors: List[str] = field(default_factory=list)
    _warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self._errors) == 0

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "platform": self.platform,
            "subdomains": self.subdomains,
            "files": self.files,
            "content_roots": self.content_roots,
            "knowledge_model_path": self.knowledge_model_path,
            "claims_path": self.claims_path,
            "api_surface_path": self.api_surface_path,
            "site_plan_path": self.site_plan_path,
            "generation_entry_points": self.generation_entry_points,
            "_errors": self._errors,
            "_warnings": self._warnings,
        }


def resolve(
    family: str,
    platform: Optional[str] = None,
    subdomains: Optional[List[str]] = None,
    file_path: Optional[str] = None,
    locale: str = "en",
) -> ScopeManifest:
    """Resolve scope for the given family/platform/subdomains."""
    errors: List[str] = []
    warnings: List[str] = []

    if not family or family not in _KNOWN_FAMILIES:
        errors.append(f"Unknown family: {family!r}")
        return ScopeManifest(
            family=family or "", platform=platform,
            subdomains=[], files=[],
            content_roots={}, knowledge_model_path=None,
            claims_path=None, api_surface_path=None, site_plan_path=None,
            generation_entry_points={},
            _errors=errors, _warnings=warnings,
        )

    if subdomains is None:
        resolved_subdomains = list(VALID_SUBDOMAINS)
    else:
        resolved_subdomains = []
        for sub in subdomains:
            if sub not in VALID_SUBDOMAINS:
                errors.append(f"Unknown subdomain: {sub!r}. Valid: {VALID_SUBDOMAINS}")
            else:
                resolved_subdomains.append(sub)

    content_roots: Dict[str, str] = {}
    for sub in resolved_subdomains:
        tmpl = _CONTENT_ROOT_TEMPLATES[sub]
        content_roots[sub] = tmpl.format(family=family, platform=platform or "")

    knowledge_base = f"knowledge/{family}/{platform}/merged" if platform else None
    knowledge_model_path = f"{knowledge_base}/model.yaml" if knowledge_base else None
    claims_path = f"{knowledge_base}/claims.json" if knowledge_base else None
    api_surface_path = f"{knowledge_base}/api_surface.json" if knowledge_base else None
    site_plan_path = f"reports/plans/{family}/{platform}/site_plan.yaml" if platform else None

    gen_points: Dict[str, dict] = {}
    for sub in resolved_subdomains:
        g = dict(_SUBDOMAIN_GENERATORS[sub])
        if sub == "reference" and platform:
            g = dict(g)
            g["command"] = g["command"].format(family=family, platform=platform)
        gen_points[sub] = g

    files: List[str] = []
    if file_path:
        sub = resolve_file_subdomain(file_path, family, platform or "")
        if sub is None or sub not in resolved_subdomains:
            errors.append(
                f"File {file_path!r} is outside declared scope "
                f"(subdomains: {resolved_subdomains})"
            )
        else:
            files = [file_path]

    return ScopeManifest(
        family=family,
        platform=platform,
        subdomains=resolved_subdomains,
        files=files,
        content_roots=content_roots,
        knowledge_model_path=knowledge_model_path,
        claims_path=claims_path,
        api_surface_path=api_surface_path,
        site_plan_path=site_plan_path,
        generation_entry_points=gen_points,
        _errors=errors,
        _warnings=warnings,
    )


def resolve_file_subdomain(file_path: str, family: str, platform: str) -> Optional[str]:
    """Return the subdomain for a content file path, or None if not recognized."""
    p = file_path.replace("\\", "/")
    checks = {
        "reference": f"content/reference.aspose.org/en/{family}/{platform}",
        "blog":      f"content/blog.aspose.org/{family}/{platform}",
        "docs":      f"content/docs.aspose.org/en/{family}/{platform}",
        "kb":        f"content/kb.aspose.org/en/{family}/{platform}",
        "products":  f"content/products.aspose.org/en/{family}/{platform}",
    }
    for sub, prefix in checks.items():
        if p.startswith(prefix):
            return sub
    return None
