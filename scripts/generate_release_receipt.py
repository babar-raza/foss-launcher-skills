"""generate_release_receipt.py -- Generate a verifiable release attestation.

Writes docs/release-receipts/<version>.json containing the version, git
commit SHA, timestamp, and CI/test evidence collected from local artifacts.

This supports R5 (Auditable) governance: each release has a persisted receipt
that an external reviewer can verify against the repository history.

Usage (from repo root, using venv interpreter):
    $ .venv/bin/python scripts/generate_release_receipt.py
    $ .venv/bin/python scripts/generate_release_receipt.py --version 0.2.0
    $ .venv/bin/python scripts/generate_release_receipt.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from scripts/ when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))


REPO_ROOT = Path(__file__).resolve().parent.parent
RECEIPTS_DIR = REPO_ROOT / "docs" / "release-receipts"


def _git_commit_sha() -> str:
    """Return the current HEAD commit SHA (short). Returns '' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _git_ref() -> str:
    """Return current branch or tag name. Returns '' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _read_version_from_pyproject() -> str:
    """Read version string from pyproject.toml. Returns '' on failure."""
    try:
        import tomllib  # Python 3.11+  # noqa: PLC0415
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]  # noqa: PLC0415
        except ImportError:
            # Fallback: naive line search
            pj = REPO_ROOT / "pyproject.toml"
            if pj.exists():
                for line in pj.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("version") and "=" in line:
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            return ""

    try:
        with open(REPO_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version", "")
    except Exception:
        return ""


def _coverage_xml_exists() -> bool:
    """Check whether a coverage.xml artifact exists (from last CI run)."""
    return (REPO_ROOT / "coverage.xml").exists()


def _read_coverage_percentage() -> "str | None":
    """Extract line-rate from coverage.xml if present. Returns percent string or None."""
    cov_xml = REPO_ROOT / "coverage.xml"
    if not cov_xml.exists():
        return None
    try:
        import xml.etree.ElementTree as ET  # noqa: N814, PLC0415
        tree = ET.parse(cov_xml)  # nosec B314 — internal CI artifact, not user-supplied
        root = tree.getroot()
        line_rate = root.get("line-rate", "")
        if line_rate:
            return f"{float(line_rate) * 100:.1f}%"
    except Exception:
        pass
    return None


def generate_receipt(version: str) -> dict:
    """Build the release receipt dict."""
    sha = _git_commit_sha()
    ref = _git_ref()
    coverage = _read_coverage_percentage()
    ci_url = None  # populated by CI via GITHUB_RUN_URL env var if present
    try:
        import os  # noqa: PLC0415
        ci_url = os.environ.get("GITHUB_RUN_URL") or None
    except Exception:
        pass

    receipt = {
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha_short": sha,
        "git_ref": ref,
        "ci_run_url": ci_url,
        "evidence": {
            "coverage_xml_present": _coverage_xml_exists(),
            "coverage_percentage": coverage,
            "security_gates": "bandit+pip-audit (see .github/workflows/pipeline-tests.yml)",
            "skill_registry": "validated by skill-registry-audit workflow",
        },
        "notes": (
            "This receipt is generated at release time to provide an auditable "
            "artifact linking version, commit, and CI evidence. It does not "
            "replace a cryptographic attestation — it is a human-readable "
            "governance artifact for the R5 (Auditable) dimension."
        ),
    }
    return receipt


def write_receipt(version: str, *, dry_run: bool = False) -> Path:
    """Write the receipt to docs/release-receipts/<version>.json.

    Parameters
    ----------
    version:
        Release version string (e.g. "0.2.0").
    dry_run:
        If True, print the receipt JSON to stdout without writing to disk.

    Returns
    -------
    Path to the written receipt file (or a dummy path if dry_run).
    """
    receipt = generate_receipt(version)
    out_path = RECEIPTS_DIR / f"{version}.json"

    if dry_run:
        print(json.dumps(receipt, indent=2))
        return out_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = argparse.ArgumentParser(
        description="Generate a release receipt attestation.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Release version (default: read from pyproject.toml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print receipt to stdout without writing to disk.",
    )
    args = parser.parse_args(argv)

    version = args.version or _read_version_from_pyproject()
    if not version:
        print("ERROR: could not determine version. Pass --version explicitly.", file=sys.stderr)
        return 1

    try:
        path = write_receipt(version, dry_run=args.dry_run)
        if not args.dry_run:
            print(f"Receipt written to: {path}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
