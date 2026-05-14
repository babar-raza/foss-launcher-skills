#!/usr/bin/env python3
"""Standalone gap-eval runner.

This restores the gap-eval executable contract without coupling to the Hugo
site repo. It performs non-destructive content discovery and profile checks,
then writes structured reports only to a configured output root unless
``--dry-run`` is used.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from scripts.content_repo_adapter import assert_write_allowed, resolve_clone_cache, resolve_content_root, resolve_output_root  # noqa: E402

_VALIDATE_PROFILE_PATH = Path(__file__).resolve().parent / "validate_profile.py"
_VALIDATE_SPEC = importlib.util.spec_from_file_location("standalone_gap_eval_validate_profile", _VALIDATE_PROFILE_PATH)
if _VALIDATE_SPEC is None or _VALIDATE_SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"Unable to load {_VALIDATE_PROFILE_PATH}")
_VALIDATE_MODULE = importlib.util.module_from_spec(_VALIDATE_SPEC)
sys.modules[_VALIDATE_SPEC.name] = _VALIDATE_MODULE
_VALIDATE_SPEC.loader.exec_module(_VALIDATE_MODULE)
profile_path = _VALIDATE_MODULE.profile_path
validate_profile_file = _VALIDATE_MODULE.validate_profile_file


SCOPES = ("all", "products", "docs", "blog", "kb", "reference")
SITE_GLOBS: dict[str, list[str]] = {
    "products": [
        "products.aspose.org/en/{family}/{platform}/**/*.md",
        "products.aspose.org/en/{family}/_index.md",
    ],
    "docs": ["docs.aspose.org/en/{family}/{platform}/**/*.md"],
    "blog": ["blog.aspose.org/{family}/{platform}/**/*.md"],
    "kb": ["kb.aspose.org/en/{family}/{platform}/**/*.md"],
    "reference": ["reference.aspose.org/en/{family}/{platform}/**/*.md"],
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    scope: str
    path: str
    message: str


def _selected_scopes(scope: str) -> list[str]:
    return list(SITE_GLOBS) if scope == "all" else [scope]


def discover_content_files(content_root: Path, family: str, platform: str, scope: str) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for site in _selected_scopes(scope):
        files: list[Path] = []
        for pattern in SITE_GLOBS[site]:
            files.extend(sorted(content_root.glob(pattern.format(family=family, platform=platform))))
        result[site] = [path for path in files if path.is_file() and not path.name.startswith("index.")]
    return result


def evaluate(
    *,
    family: str,
    platform: str,
    scope: str,
    content_root: Path,
    clone_cache: Path,
    no_llm: bool,
) -> dict[str, Any]:
    profile_ok, profile_errors, profile = validate_profile_file(family, platform)
    clone_path = clone_cache / f"aspose_{family}_{platform}"
    discovered = discover_content_files(content_root, family, platform, scope)

    findings: list[Finding] = []
    if not profile_ok:
        findings.append(
            Finding("S", "PROFILE", "all", str(profile), "; ".join(profile_errors))
        )
    if not clone_path.exists():
        findings.append(
            Finding(
                "S",
                "CLONE_CACHE",
                "all",
                str(clone_path),
                "Clone cache missing; deterministic clone-grounded checks were not executed.",
            )
        )
    for site, files in discovered.items():
        if not files:
            findings.append(
                Finding("I", "NO_CONTENT", site, str(content_root), f"No Markdown files discovered for {site}.")
            )

    major = [item for item in findings if item.severity == "M"]
    standard = [item for item in findings if item.severity == "S"]
    if major:
        verdict = "NOT PUBLISHABLE"
    elif standard:
        verdict = "CONDITIONAL"
    else:
        verdict = "PUBLICATION READY"

    return {
        "schema_version": 1,
        "runner": "standalone-gap-eval-scaffold",
        "family": family,
        "platform": platform,
        "scope": scope,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "content_root": str(content_root),
        "clone_cache": str(clone_cache),
        "clone_path": str(clone_path),
        "profile": str(profile),
        "profile_ok": profile_ok,
        "tier_1_deterministic": "scaffold",
        "tier_2_vector": "not_implemented",
        "tier_3_llm": "disabled" if no_llm else "not_implemented",
        "discovered_counts": {site: len(files) for site, files in discovered.items()},
        "discovered_files": {
            site: [str(path.relative_to(content_root)) for path in files]
            for site, files in discovered.items()
        },
        "findings": [asdict(item) for item in findings],
        "verdict": verdict,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Gap Eval Report - {report['family']}/{report['platform']}",
        "",
        f"- Verdict: `{report['verdict']}`",
        f"- Scope: `{report['scope']}`",
        f"- Runner: `{report['runner']}`",
        f"- Content root: `{report['content_root']}`",
        f"- Clone cache: `{report['clone_cache']}`",
        "",
        "## Discovered Content",
        "",
    ]
    for site, count in report["discovered_counts"].items():
        lines.append(f"- `{site}`: {count}")
    lines.extend(["", "## Findings", ""])
    if report["findings"]:
        for item in report["findings"]:
            lines.append(f"- `{item['severity']}` `{item['code']}` `{item['scope']}`: {item['message']}")
    else:
        lines.append("- No scaffold-level findings.")
    lines.extend([
        "",
        "## Implementation Notes",
        "",
        "- This standalone runner verifies discovery, profile availability, clone-cache path resolution, and report generation.",
        "- Full Tier 2 vector and Tier 3 LLM parity remain tracked migration work.",
        "",
    ])
    return "\n".join(lines)


def output_paths(output_root: Path, family: str, platform: str, out: str | None) -> tuple[Path, Path]:
    if out:
        target = Path(out).expanduser().resolve()
        return target.with_suffix(".md"), target.with_suffix(".json")
    base = output_root / "gap-analysis"
    return base / f"{family}-{platform}.md", base / f"{family}-{platform}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--scope", choices=SCOPES, default="all")
    parser.add_argument("--content-root")
    parser.add_argument("--output-root")
    parser.add_argument("--out")
    parser.add_argument("--state-dir")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    del args.state_dir

    config = {"content_root": args.content_root} if args.content_root else None
    try:
        content_root = resolve_content_root(config, os.environ)
        output_root = resolve_output_root(args.output_root)
        clone_cache = resolve_clone_cache()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = evaluate(
        family=args.family,
        platform=args.platform,
        scope=args.scope,
        content_root=content_root,
        clone_cache=clone_cache,
        no_llm=args.no_llm,
    )
    md_path, json_path = output_paths(output_root, args.family, args.platform, args.out)
    if args.dry_run:
        print(json.dumps(report, indent=2))
        return 0

    try:
        assert_write_allowed(md_path, dry_run=False)
        assert_write_allowed(json_path, dry_run=False)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report), encoding="utf-8")
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        print(f"error: failed to write report: {exc}", file=sys.stderr)
        return 3

    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
