"""dependency_resolver.py — Verify whether a broken internal link target should exist.

Given a broken URL found by StructureEvaluator (cause_class=UPSTREAM_MISSING or
BAD_LINK_FORMAT), this module determines the correct remediation verdict:

  GENERATE      — page does not exist but class is in api_surface.json → run S-62/S-60
  CORRECT_LINK  — page exists under a different slug/casing → run S-73 (body-wording)
  ESCALATE      — class absent from api_surface.json or knowledge unavailable → human queue

Usage (CLI):
    python -m scripts.pipeline.dependency_resolver \\
        --url "https://reference.aspose.org/slides/net/effects/" \\
        --family slides --platform net \\
        --out reports/dependency-backtrack/slides-net-20260403/dependency-verification.json

Usage (library):
    from scripts.pipeline.dependency_resolver import DependencyVerifier
    result = DependencyVerifier(repo_root=Path(".")).verify(
        url="https://reference.aspose.org/slides/net/effects/",
        family="slides", platform="net",
    )
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_ASPOSE_URL_RE = re.compile(
    r"(?:https?://|/)?((?:reference|docs|kb|blog|products)\.aspose\.org)"
    r"(/[^\s)\"'#?]*)",
    re.IGNORECASE,
)

_CONTENT_ROOT = Path("content")


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class DependencyVerificationRecord:
    """Result of verifying a single broken link target."""

    source_url: str
    subdomain: str           # e.g. "reference.aspose.org"
    target_slug: str         # e.g. "EffectFormat" (last path segment)
    family: str
    platform: str

    # Filesystem / knowledge checks
    page_exists: bool
    url_format_mismatch: bool    # page exists but under different casing/slug
    api_surface_match: bool      # class name found in api_surface.json
    knowledge_stale: bool        # model.yaml has stale_since != null

    # Final verdict
    verdict: str             # GENERATE | CORRECT_LINK | ESCALATE
    verdict_reason: str
    correct_url: Optional[str] = None   # populated when verdict == CORRECT_LINK


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class DependencyVerifier:
    """Resolve a broken internal link to a concrete remediation verdict."""

    def __init__(self, repo_root: Path = Path(".")):
        self.repo_root = repo_root.resolve()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def verify(self, url: str, family: str, platform: str) -> DependencyVerificationRecord:
        """Produce a DependencyVerificationRecord for a broken link URL."""

        m = _ASPOSE_URL_RE.search(url)
        if not m:
            return DependencyVerificationRecord(
                source_url=url, subdomain="", target_slug="",
                family=family, platform=platform,
                page_exists=False, url_format_mismatch=False,
                api_surface_match=False, knowledge_stale=False,
                verdict="ESCALATE",
                verdict_reason="URL does not match any recognised aspose.org subdomain pattern",
            )

        subdomain = m.group(1).lower()
        path_part = m.group(2).rstrip("/")
        segments = [s for s in path_part.split("/") if s]
        if segments and segments[0] == "en":
            segments = segments[1:]

        target_slug = segments[-1] if segments else ""

        page_exists, url_format_mismatch, correct_url = self._check_page_exists(
            subdomain, segments
        )
        api_surface_match = self._check_api_surface(family, platform, target_slug)
        knowledge_stale = self._check_knowledge_stale(family, platform)

        # --- Verdict logic ---
        if knowledge_stale and not page_exists:
            verdict = "ESCALATE"
            reason = (
                f"Knowledge model for {family}/{platform} is stale "
                "(stale_since != null). Run S-12 → S-14 before generating content."
            )
        elif page_exists and url_format_mismatch:
            verdict = "CORRECT_LINK"
            reason = (
                f"Page exists under a different URL slug. "
                f"Correct the link in the source page to point to: {correct_url}"
            )
        elif not page_exists and api_surface_match:
            verdict = "GENERATE"
            reason = (
                f"Class `{target_slug}` exists in api_surface.json for {family}/{platform} "
                "but no reference page exists. Run S-62 (batch-reference) to generate it."
            )
        elif not page_exists and not api_surface_match:
            verdict = "ESCALATE"
            reason = (
                f"Target slug `{target_slug}` is neither a known class in api_surface.json "
                "nor an existing page. The link may be incorrect. Human review required."
            )
        else:  # page_exists and not url_format_mismatch — should have been "OK"
            verdict = "ESCALATE"
            reason = (
                "Page exists and URL appears correct but was flagged as broken. "
                "Possible stale evaluation result. Re-run content_eval."
            )

        return DependencyVerificationRecord(
            source_url=url,
            subdomain=subdomain,
            target_slug=target_slug,
            family=family,
            platform=platform,
            page_exists=page_exists,
            url_format_mismatch=url_format_mismatch,
            api_surface_match=api_surface_match,
            knowledge_stale=knowledge_stale,
            verdict=verdict,
            verdict_reason=reason,
            correct_url=correct_url,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_page_exists(
        self, subdomain: str, segments: list[str]
    ) -> tuple[bool, bool, Optional[str]]:
        """Return (page_exists, url_format_mismatch, correct_url).

        Checks exact match first, then case-insensitive match.
        """
        base = self.repo_root / _CONTENT_ROOT / subdomain / "en"
        slug_path = Path(*segments) if segments else Path(".")

        # Exact match candidates
        exact_candidates = [
            base / slug_path / "_index.md",
            base / slug_path / "index.md",
        ]
        if segments:
            exact_candidates.append(
                base / slug_path.parent / (slug_path.name + ".md")
            )

        for c in exact_candidates:
            if c.exists():
                return True, False, None

        # Case-insensitive search
        if segments:
            parent_path = (
                base / Path(*segments[:-1]) if len(segments) > 1 else base
            )
            target_lower = segments[-1].lower()
            if parent_path.is_dir():
                for child in parent_path.iterdir():
                    child_stem = (
                        child.stem if child.suffix == ".md" else child.name
                    )
                    if child_stem.lower() == target_lower and child_stem != segments[-1]:
                        # Build the correct URL
                        correct_segments = segments[:-1] + [child_stem]
                        correct_url = (
                            "https://" + subdomain + "/en/"
                            + "/".join(correct_segments) + "/"
                        )
                        return True, True, correct_url

        return False, False, None

    def _check_api_surface(self, family: str, platform: str, slug: str) -> bool:
        """Return True if slug (class/enum/interface name) appears in api_surface.json.

        api_surface.json is a flat list of entries, each with a "name" key and a
        "kind" key (e.g. "class_declaration", "enum_declaration", "interface_declaration").
        """
        if not slug:
            return False
        surface_path = (
            self.repo_root / "knowledge" / family / platform / "merged" / "api_surface.json"
        )
        if not surface_path.exists():
            return False
        try:
            data = json.loads(surface_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False

        entries = data if isinstance(data, list) else []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("name") == slug:
                return True
            if isinstance(entry, str) and entry == slug:
                return True
        return False

    def _check_knowledge_stale(self, family: str, platform: str) -> bool:
        """Return True if model.yaml has stale_since != null."""
        model_path = (
            self.repo_root / "knowledge" / family / platform / "model.yaml"
        )
        if not model_path.exists():
            return False
        try:
            import yaml
            data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            return bool(data.get("stale_since"))
        except Exception:
            return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify whether a broken internal link needs generation, "
                    "link correction, or human escalation."
    )
    parser.add_argument("--url", required=True, help="The broken link URL to verify")
    parser.add_argument("--family", required=True, help="Product family (e.g. slides)")
    parser.add_argument("--platform", required=True, help="Platform (e.g. net)")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: .)")
    parser.add_argument(
        "--out", default=None,
        help="Write DependencyVerificationRecord JSON to this path"
    )
    args = parser.parse_args()

    verifier = DependencyVerifier(repo_root=Path(args.repo_root))
    result = verifier.verify(
        url=args.url, family=args.family, platform=args.platform
    )

    record = asdict(result)
    print(json.dumps(record, indent=2))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"\nRecord written to: {out_path}", file=sys.stderr)

    # Exit code signals the verdict to the caller.
    exit_codes = {"GENERATE": 10, "CORRECT_LINK": 11, "ESCALATE": 12}
    sys.exit(exit_codes.get(result.verdict, 1))


if __name__ == "__main__":
    main()
