"""extraction/claims.py — Identity claim generation from package manifest.

Extracted from scout.py (step 4.5). Standalone function usable without the
Scout class.

Public API::

    build_identity_claims(manifest, family) -> list[dict]
"""
from __future__ import annotations

import hashlib


def build_identity_claims(manifest: dict, family: str) -> list[dict]:
    """Build install/license/dependency claims from the package manifest.

    Returns a list of claim dicts in scout format.
    """
    claims: list[dict] = []

    def _add(kind: str, text: str) -> None:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
        claims.append({
            "claim_id": f"CLM-{family}-{h}",
            "kind": kind,
            "text": text,
            "confidence": 1.0,
            "claim_source": "scout",
            "evidence": [],
        })

    name = manifest.get("name", "")
    version = manifest.get("version", "")
    lic = manifest.get("license", "")

    if name:
        _add("install", f"Package name is {name}")
    if version:
        _add("install", f"Current version is {version}")
    if lic:
        _add("license", f"Licensed under {lic}")

    deps = manifest.get("dependencies", [])
    for dep in deps[:50]:
        if isinstance(dep, str):
            _add("dependency", f"Depends on {dep}")

    return claims
