#!/usr/bin/env python3
"""Validate gap-eval product profiles against their clone caches.

Usage:
    python scripts/gap-eval/src/validate_profile.py {family} {platform}
    python scripts/gap-eval/src/validate_profile.py --all
    python scripts/gap-eval/src/validate_profile.py --update {family} {platform}
    python scripts/gap-eval/src/validate_profile.py --update {family} {platform} --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_PROFILES_DIR = _REPO_ROOT / "scripts" / "gap-eval" / "profiles"


_DEFAULT_PROFILES_DIR = _REPO_ROOT / "scripts" / "gap-eval" / "profiles"


def configure(
    *,
    repo_root: "Path | str | None" = None,
    profiles_dir: "Path | str | None" = None,
) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _PROFILES_DIR
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _PROFILES_DIR = Path(profiles_dir) if profiles_dir is not None else _DEFAULT_PROFILES_DIR

ALL_PRODUCTS = [
    ("3d", "java"),
    ("3d", "net"),
    ("3d", "python"),
    ("3d", "typescript"),
    ("cells", "net"),
    ("cells", "python"),
    ("email", "cpp"),
    ("email", "net"),
    ("email", "python"),
    ("note", "python"),
    ("slides", "cpp"),
    ("slides", "java"),
    ("slides", "net"),
    ("slides", "python"),
    ("words", "python"),
]


def _clone_cache_base() -> Path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
    from core.clone_cache import cache_root  # noqa: PLC0415
    return cache_root()


def _read_package_from_build_file(build_file: Path) -> str | None:
    """Extract package name from a build file using heuristic patterns."""
    try:
        text = build_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Maven pom.xml: prefer groupId:artifactId combo (canonical Maven coordinate)
    m_g = re.search(r"<groupId>([\w.]+)</groupId>", text)
    m_a = re.search(r"<artifactId>([\w.\-]+)</artifactId>", text)
    if m_g and m_a:
        return f"{m_g.group(1)}:{m_a.group(1)}"
    for pat in [
        r"<groupId>([\w.]+)</groupId>",
        r"<artifactId>([\w.\-]+)</artifactId>",
        r"""name\s*=\s*['"]([^'"]+)['"]""",
        r'"name":\s*"([^"]+)"',
        r"<PackageId>([\w.]+)</PackageId>",
        # Fallback: some .csproj files use <AssemblyName> without <PackageId>
        # (e.g. Aspose.Cells_FOSS). Must be last — PackageId is the canonical element.
        r"<AssemblyName>([\w.]+)</AssemblyName>",
    ]:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def update_profile(family: str, platform: str, dry_run: bool = False) -> bool:
    """Derive discovered_actuals.package_name from clone cache and write it to the profile.

    Returns True on success, False if the package name could not be determined.
    Safe to re-run: only writes when the derived value differs from the stored one.
    Requires clone cache to be available locally — not intended for CI.
    """
    profile_path = _PROFILES_DIR / family / f"{platform}.yaml"
    if not profile_path.exists():
        log.error("Profile not found: %s", profile_path)
        return False

    try:
        import yaml  # type: ignore
    except ImportError:
        log.error("PyYAML is required for --update (pip install pyyaml)")
        return False

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    hints = profile.get("discovery_hints") or {}
    pkg_source = hints.get("package_source_file")
    if not pkg_source:
        log.error("%s/%s: discovery_hints.package_source_file is missing — cannot auto-derive", family, platform)
        return False

    try:
        cache_base = _clone_cache_base()
    except (FileNotFoundError, OSError) as exc:
        log.error("Cannot resolve clone cache base (%s) — clone cache required for --update", exc)
        return False

    build_file = cache_base / f"aspose_{family}_{platform}" / pkg_source
    if not build_file.exists():
        log.error("Build file not found: %s", build_file)
        return False

    derived = _read_package_from_build_file(build_file)
    if not derived:
        log.error("Could not extract package name from %s", build_file)
        return False

    current = (profile.get("discovered_actuals") or {}).get("package_name")
    if current == derived:
        log.info("SKIP %s/%s: discovered_actuals.package_name already up-to-date (%s)", family, platform, derived)
        return True

    log.info(
        "%s/%s: %s discovered_actuals.package_name: %r → %r",
        family, platform,
        "would set" if dry_run else "setting",
        current, derived,
    )
    if dry_run:
        return True

    # Write back: update only the package_name key, preserve everything else.
    if "discovered_actuals" not in profile or profile["discovered_actuals"] is None:
        profile["discovered_actuals"] = {}
    profile["discovered_actuals"]["package_name"] = derived
    profile_path.write_text(yaml.dump(profile, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    log.info("UPDATED %s/%s", family, platform)
    return True


def _load_profile_yaml(profile_path: Path) -> tuple[dict, list[str]]:
    """Parse profile YAML; return (profile_dict, errors).

    On ImportError (no pyyaml): falls back to substring checks, returns partial dict {}.
    On parse error: returns ({}, [error_string]).
    """
    try:
        import yaml  # type: ignore
        return yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}, []
    except ImportError:
        errors: list[str] = []
        content = profile_path.read_text(encoding="utf-8")
        if "discovery_hints" not in content:
            errors.append("Profile missing 'discovery_hints' section")
        if "expected_sections" not in content:
            errors.append("Profile missing 'expected_sections' section")
        return {}, errors
    except (FileNotFoundError, OSError) as exc:
        return {}, [f"Profile YAML parse error: {exc}"]


def validate_schema(family: str, platform: str) -> list[str]:
    """Validate profile YAML structure only — no clone cache required.

    Checks: file existence, YAML parseability, required fields, non-empty sections.
    Safe to run in CI environments where no clone cache is present.
    Returns list of error strings (empty = pass).
    """
    errors: list[str] = []
    profile_path = _PROFILES_DIR / family / f"{platform}.yaml"

    # S-1. Profile file exists
    if not profile_path.exists():
        errors.append(f"Profile file missing: {profile_path}")
        return errors

    # S-2. Profile is parseable YAML
    profile, parse_errors = _load_profile_yaml(profile_path)
    errors.extend(parse_errors)
    if any("parse error" in e for e in parse_errors):
        return errors  # unparseable — remaining checks meaningless

    # S-3. expected_sections is non-empty
    sections = profile.get("expected_sections") or []
    if not sections:
        errors.append("expected_sections is empty")

    # S-4. package_source_file is declared
    hints = profile.get("discovery_hints") or {}
    if not hints.get("package_source_file"):
        errors.append("discovery_hints.package_source_file is missing")

    # S-5. package_name is populated
    actuals = profile.get("discovered_actuals") or {}
    if not actuals.get("package_name"):
        errors.append("discovered_actuals.package_name is null — run gap-eval to populate")

    return errors


def validate_against_cache(family: str, platform: str, cache_base: Path) -> list[str]:
    """Cross-validate profile against clone cache — requires cache_base to exist.

    Checks: per-product cache dir exists, package_source_file resolves, package_name
    matches the build file.  Schema correctness is assumed (run validate_schema first).
    Returns list of error strings (empty = pass).

    CI enforcement boundary note:
    - validate_schema() catches null/missing package_name in every CI environment
      (no clone cache required).  This is the only check that fires unconditionally.
    - This function (validate_against_cache) catches wrong-but-present package_name
      values, but only when a clone cache exists.  In GitHub Actions the clone cache
      is never present, so this check is gracefully skipped there (exit 0, [SKIP] log).
    - Proof: run 24245690202 on 2026-04-10 confirmed schema-fail exits 1 in CI.
      Cache cross-validation cannot be proven in CI without caches — use locally.
    """
    errors: list[str] = []
    profile_path = _PROFILES_DIR / family / f"{platform}.yaml"

    profile, _ = _load_profile_yaml(profile_path)
    if not profile:
        return errors  # schema errors already surfaced by validate_schema

    cache_path = cache_base / f"aspose_{family}_{platform}"
    if not cache_path.exists():
        errors.append(f"Clone cache not found: {cache_path}")
        return errors

    hints = profile.get("discovery_hints") or {}
    pkg_source = hints.get("package_source_file")
    if not pkg_source:
        return errors  # missing field already caught by validate_schema

    pkg_path = cache_path / pkg_source
    if not pkg_path.exists():
        errors.append(
            f"Package source hint '{pkg_source}' not found in clone cache "
            f"(tried {pkg_path})"
        )
        return errors

    # Cross-check: profile package_name must match clone cache build file
    actuals = profile.get("discovered_actuals") or {}
    stored_pkg = actuals.get("package_name")
    if stored_pkg:
        actual_pkg = _read_package_from_build_file(pkg_path)
        if actual_pkg and actual_pkg != stored_pkg:
            errors.append(
                f"discovered_actuals.package_name '{stored_pkg}' "
                f"does not match clone cache build file '{actual_pkg}'"
            )

    return errors


def validate_profile(family: str, platform: str) -> list[str]:
    """Validate a single profile (schema + cache).  Returns list of error strings.

    Deprecated calling convention kept for backward compatibility.
    Calls validate_schema() then validate_against_cache() when the cache exists.
    """
    errors = validate_schema(family, platform)
    if any("parse error" in e for e in errors):
        return errors  # unparseable — cache check meaningless

    try:
        cache_base = _clone_cache_base()
    except (FileNotFoundError, OSError, ImportError):
        return errors  # no cache — return schema results only

    if cache_base.exists():
        errors += validate_against_cache(family, platform, cache_base)
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate gap-eval profiles against clone caches.")
    parser.add_argument("--update", action="store_true",
                        help="Derive and write discovered_actuals.package_name from clone cache (local only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --update: show what would change without writing")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Validate all profiles")
    group.add_argument("family", nargs="?", help="Product family")
    parser.add_argument("platform", nargs="?", help="Platform")
    args = parser.parse_args()

    if args.all:
        targets = ALL_PRODUCTS
    elif args.family and args.platform:
        targets = [(args.family, args.platform)]
    else:
        parser.error("Provide --all OR both family and platform")
        return

    if args.update:
        any_failures = False
        for family, platform in targets:
            if not update_profile(family, platform, dry_run=args.dry_run):
                any_failures = True
        if any_failures:
            sys.exit(1)
        return

    any_errors = False

    # Pass 1 — Schema validation: always runs, no clone cache required.
    # Catches structural errors (missing file, unparseable YAML, empty sections,
    # missing required fields) in every CI environment.
    for family, platform in targets:
        schema_errors = validate_schema(family, platform)
        label = f"{family}/{platform}"
        if schema_errors:
            any_errors = True
            log.error("FAIL %s (schema):", label)
            for err in schema_errors:
                log.error("  - %s", err)

    # Pass 2 — Cache cross-validation: only when clone caches are present.
    # Skips gracefully in CI environments without caches; logs [SKIP] at WARNING.
    try:
        cache_base = _clone_cache_base()
        if not cache_base.exists():
            log.warning(
                "[SKIP] Clone cache base %s does not exist — "
                "cache cross-validation skipped (schema pass above still enforced)",
                cache_base,
            )
        else:
            for family, platform in targets:
                cache_errors = validate_against_cache(family, platform, cache_base)
                label = f"{family}/{platform}"
                if cache_errors:
                    any_errors = True
                    log.error("FAIL %s (cache):", label)
                    for err in cache_errors:
                        log.error("  - %s", err)
                elif not validate_schema(family, platform):
                    # Only log PASS when both schema and cache pass
                    log.info("PASS %s", label)
    except (FileNotFoundError, OSError, ImportError) as exc:
        log.warning(
            "[SKIP] Cannot resolve clone cache base (%s) — "
            "cache cross-validation skipped (schema pass above still enforced)",
            exc,
        )

    if any_errors:
        sys.exit(1)
    elif not any(validate_schema(f, p) for f, p in targets):
        log.info("All profiles validated successfully.")


if __name__ == "__main__":
    main()
