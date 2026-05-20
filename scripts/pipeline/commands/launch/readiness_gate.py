# Adapted from aspose.org
#!/usr/bin/env python3
"""readiness_gate.py -- Unified production readiness gate (TC-08).

Aggregates all system-level readiness signals into a single pass/fail verdict:

  G-01  Skill sync parity      -- sync_skills.py --check exits 0
  G-02  Provider sync          -- sync_providers.py --dry-run exits 0
  G-03  DAR coverage           -- check_dar_coverage.py exits 0
  G-04  Knowledge staleness    -- knowledge model stale_since must be null
  G-05  Proof index complete   -- every directory in reports/proofs/ is in INDEX.json
  G-06  Launch gate            -- launch_gate.py {family} {platform} exits 0

Usage:
    python scripts/pipeline/commands/launch/readiness_gate.py {family} {platform}
    python scripts/pipeline/commands/launch/readiness_gate.py note python
    python scripts/pipeline/commands/launch/readiness_gate.py note python --skip-launch-gate

Flags:
    --skip-launch-gate   Skip G-06 (launch_gate) for faster system-level check

Exit codes:
    0   All gates pass -- system is ready
    1   One or more gates failed -- not ready

Created: 2026-04-25 (TC-08)
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Stdout encoding safety (Windows CP1252 compatibility)
# ---------------------------------------------------------------------------

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

import os

_HERE = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(_HERE.parents[3])))
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


# Prefer the project virtualenv; fall back to system Python.
_VENV_PYTHON_WIN = _DEFAULT_REPO_ROOT / ".venv" / "Scripts" / "python.exe"
_VENV_PYTHON_UNIX = _DEFAULT_REPO_ROOT / ".venv" / "bin" / "python"

if _VENV_PYTHON_WIN.exists():
    _PYTHON = str(_VENV_PYTHON_WIN)
elif _VENV_PYTHON_UNIX.exists():
    _PYTHON = str(_VENV_PYTHON_UNIX)
else:
    print(
        "ERROR: readiness_gate: .venv not found at repo root.\n"
        "  Recovery: bash scripts/ci/hooks/repair_venv.sh\n"
        "  Or run: /getting-started",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"


class GateResult:
    def __init__(self, gate_id: str, name: str, status: str, detail: str) -> None:
        self.gate_id = gate_id
        self.name = name
        self.status = status
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.gate_id} [{self.status:<4}] {self.name}: {self.detail}"


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> tuple[int, str]:
    """Run *cmd*, return (returncode, combined_output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        combined = (result.stdout + result.stderr).strip()
        return result.returncode, combined
    except FileNotFoundError as exc:
        return 1, f"Command not found: {exc}"


# ---------------------------------------------------------------------------
# Gate implementations
# ---------------------------------------------------------------------------

def gate_g01_skill_sync(env: dict | None = None) -> GateResult:
    """G-01: sync_skills.py --check exits 0."""
    script = _REPO_ROOT / "scripts" / "pipeline" / "sync_skills.py"
    rc, out = _run([_PYTHON, str(script), "--check"])
    if rc == 0:
        return GateResult("G-01", "Skill sync parity", STATUS_PASS, "sync_skills --check passed")
    return GateResult("G-01", "Skill sync parity", STATUS_FAIL, f"sync_skills --check exited {rc}: {out[:200]}")


def gate_g02_provider_sync(env: dict | None = None) -> GateResult:
    """G-02: sync_providers.py --dry-run exits 0."""
    script = _REPO_ROOT / "scripts" / "pipeline" / "sync_providers.py"
    rc, out = _run([_PYTHON, str(script), "--dry-run"])
    if rc == 0:
        return GateResult("G-02", "Provider sync", STATUS_PASS, "sync_providers --dry-run passed")
    return GateResult("G-02", "Provider sync", STATUS_FAIL, f"sync_providers --dry-run exited {rc}: {out[:200]}")


def gate_g03_dar_coverage(env: dict | None = None) -> GateResult:
    """G-03: check_dar_coverage.py exits 0."""
    script = _REPO_ROOT / "scripts" / "ci" / "check_dar_coverage.py"
    rc, out = _run([_PYTHON, str(script)])
    if rc == 0:
        return GateResult("G-03", "DAR coverage", STATUS_PASS, "check_dar_coverage passed")
    lines = out.split("\n")
    summary = next((l for l in lines if l.startswith("Summary:")), out[:200])
    return GateResult("G-03", "DAR coverage", STATUS_FAIL, summary)


def gate_g04_knowledge_staleness(family: str, platform: str) -> GateResult:
    """G-04: knowledge model stale_since must be null."""
    model_path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return GateResult(
            "G-04", "Knowledge staleness", STATUS_FAIL,
            f"model.yaml not found: knowledge/{family}/{platform}/merged/model.yaml",
        )
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return GateResult("G-04", "Knowledge staleness", STATUS_FAIL, f"model.yaml parse error: {exc}")
    stale_since = data.get("stale_since")
    if stale_since is None:
        return GateResult("G-04", "Knowledge staleness", STATUS_PASS, "stale_since: null (fresh)")
    return GateResult(
        "G-04", "Knowledge staleness", STATUS_FAIL,
        f"stale_since: {stale_since} — refresh knowledge before shipping",
    )


def gate_g05_proof_index(env: dict | None = None) -> GateResult:
    """G-05: every directory in reports/proofs/ must be registered in INDEX.json."""
    proofs_dir = _REPO_ROOT / "reports" / "proofs"
    index_path = proofs_dir / "INDEX.json"
    if not proofs_dir.exists():
        return GateResult("G-05", "Proof index complete", STATUS_SKIP, "reports/proofs/ not found (local-only)")
    if not index_path.exists():
        return GateResult("G-05", "Proof index complete", STATUS_FAIL, "INDEX.json missing")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        registered = {entry.get("bundle_id") for entry in index}
    except Exception as exc:
        return GateResult("G-05", "Proof index complete", STATUS_FAIL, f"INDEX.json parse error: {exc}")
    dirs = {d.name for d in proofs_dir.iterdir() if d.is_dir()}
    unregistered = dirs - registered
    if not unregistered:
        return GateResult("G-05", "Proof index complete", STATUS_PASS, f"{len(registered)} bundles registered")
    return GateResult(
        "G-05", "Proof index complete", STATUS_FAIL,
        f"{len(unregistered)} unregistered bundle(s): {', '.join(sorted(unregistered))}",
    )


def gate_g06_launch_gate(family: str, platform: str) -> GateResult:
    """G-06: launch_gate.py exits 0."""
    script = _REPO_ROOT / "scripts" / "pipeline" / "launch_gate.py"
    rc, out = _run([_PYTHON, str(script), family, platform, "--skip-tests"])
    if rc == 0:
        return GateResult("G-06", "Launch gate", STATUS_PASS, f"launch_gate {family}/{platform} passed")
    lines = out.split("\n")
    fail_lines = [l for l in lines if "FAIL" in l]
    summary = "; ".join(fail_lines[:3]) if fail_lines else out[:200]
    return GateResult("G-06", "Launch gate", STATUS_FAIL, summary)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified production readiness gate")
    parser.add_argument("family", help="Product family (e.g. note)")
    parser.add_argument("platform", help="Platform (e.g. python)")
    parser.add_argument("--skip-launch-gate", action="store_true",
                        help="Skip G-06 (launch_gate) for faster system-level check")
    args = parser.parse_args(argv)

    family = args.family
    platform = args.platform

    print(f"=== Unified Readiness Gate: {family}/{platform} ===")
    print()

    gates: list[GateResult] = []
    gates.append(gate_g01_skill_sync())
    gates.append(gate_g02_provider_sync())
    gates.append(gate_g03_dar_coverage())
    gates.append(gate_g04_knowledge_staleness(family, platform))
    gates.append(gate_g05_proof_index())

    if args.skip_launch_gate:
        gates.append(GateResult("G-06", "Launch gate", STATUS_SKIP, "skipped via --skip-launch-gate"))
    else:
        gates.append(gate_g06_launch_gate(family, platform))

    failures: list[GateResult] = []
    for gate in gates:
        print(f"  {gate}")
        if gate.status == STATUS_FAIL:
            failures.append(gate)

    print()
    if failures:
        print(f"VERDICT: NOT READY — {len(failures)} gate(s) failed:")
        for g in failures:
            # Show only first line of detail in summary to keep verdict readable
            first_line = g.detail.split("\n")[0]
            print(f"  [BLOCKER] {g.gate_id} {g.name}: {first_line}")
        return 1
    else:
        passing = [g for g in gates if g.status == STATUS_PASS]
        skipped = [g for g in gates if g.status == STATUS_SKIP]
        print(f"VERDICT: READY — {len(passing)} gate(s) passed" +
              (f", {len(skipped)} skipped" if skipped else ""))
        return 0


if __name__ == "__main__":
    sys.exit(main())
