#!/usr/bin/env python3
"""Validate standalone gap-eval product profiles."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE_ROOT = REPO_ROOT / "scripts" / "gap-eval" / "profiles"
REQUIRED_KEYS = ("family", "platform")


def profile_path(family: str, platform: str) -> Path:
    return PROFILE_ROOT / family / f"{platform}.yaml"


def load_profile(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML is required to validate nested gap-eval profiles") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Profile root must be a mapping")
    return data


def validate_profile(data: dict[str, Any], *, family: str, platform: str) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_KEYS:
        if not data.get(key):
            errors.append(f"missing required key: {key}")
    if data.get("family") and data.get("family") != family:
        errors.append(f"family mismatch: expected {family}, found {data.get('family')}")
    if data.get("platform") and data.get("platform") != platform:
        errors.append(f"platform mismatch: expected {platform}, found {data.get('platform')}")
    for key in ("discovery_hints", "discovered_actuals", "language_conventions"):
        if key in data and not isinstance(data[key], dict):
            errors.append(f"{key} must be a mapping")
    if "expected_sections" in data and not isinstance(data["expected_sections"], list):
        errors.append("expected_sections must be a list")
    return errors


def validate_profile_file(family: str, platform: str) -> tuple[bool, list[str], Path]:
    path = profile_path(family, platform)
    try:
        data = load_profile(path)
    except FileNotFoundError:
        return False, [f"profile not found: {path}"], path
    except Exception as exc:
        return False, [f"profile load failed: {exc}"], path
    errors = validate_profile(data, family=family, platform=platform)
    return not errors, errors, path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    ok, errors, path = validate_profile_file(args.family, args.platform)
    payload = {"ok": ok, "profile": str(path), "errors": errors}
    if args.json:
        print(json.dumps(payload, indent=2))
    elif ok:
        print(f"PASS: profile valid: {path}")
    else:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
