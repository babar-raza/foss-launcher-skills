#!/usr/bin/env python3
"""readiness_gate.py -- Unified production readiness gate (TC-08).

Aggregates all system-level readiness signals into a single pass/fail verdict:

  G-01  Skill sync parity      -- sync_skills.py --check exits 0
  G-02  Provider sync          -- sync_providers.py --dry-run exits 0
  G-03  DAR coverage           -- check_dar_coverage.py exits 0
  G-04  Knowledge staleness    -- knowledge model stale_since must be null
  G-05  Proof index complete   -- every directory in reports/proofs/ is in INDEX.json
  G-06  Launch gate            -- launch_gate.py {family} {platform} exits 0
  G-07  Cross-platform consistency -- cross_platform_audit.py {family} --json exits 0
  G-07  Cross-platform consistency -- cross_platform_audit.py {family} exits 0
  G-08  Extraction fidelity (advisory) -- scout_fidelity.py {family} {platform} --json;
        NEVER produces STATUS_FAIL today (TC-MT040-41 / D-2 Decision 13: no
        probe may block until a zero-false-positive fleet calibration
        enables it per probe -- see scout_fidelity.PROBE_FAIL_ENABLED).
        Evaluated and reported independently of G-03: G-03's DAR-coverage
        FAIL is a separate, pre-existing, repo-wide condition (MT039 G5-22)
        that must never suppress or gate G-08's own result.

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

_HERE = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = _HERE.parent.parent.parent.parent
_REPO_ROOT = _DEFAULT_REPO_ROOT

# FRESH-001 (2026-08-14): unconditional (not only inside configure()) so bare
# imports of freshness_guard resolve from gate_g04_knowledge_staleness() even when
# configure() is never explicitly called, which is the normal production case
# (module-level _REPO_ROOT is used as-is).
_REAL_LIB_DIR = str(_HERE.parent.parent / "lib")  # commands/launch/ -> commands/ -> pipeline/ -> lib/
if _REAL_LIB_DIR not in sys.path:
    sys.path.insert(0, _REAL_LIB_DIR)


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    # FRESH-001 (2026-08-14): keep freshness_guard's module-level paths in lockstep
    # with this module's own configure() -- see batch_reference.py for the same
    # pattern/rationale. G-04 is a launch-blocking readiness gate, migrated last
    # per the plan's low-to-high blast-radius rollout order. (_REAL_LIB_DIR is
    # already unconditionally on sys.path at module load -- see above -- so this
    # only needs to propagate the repo_root override.)
    try:
        import freshness_guard as _freshness_guard
        _freshness_guard.configure(repo_root=_REPO_ROOT)
    except ImportError:
        pass


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
# TC-MT040-41 (D-2/G-08): advisory-only status -- printed like any other
# gate result but deliberately excluded from the failures list in main()
# below (only STATUS_FAIL triggers a non-zero exit / NOT READY verdict).
STATUS_WARN = "WARN"


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
    script = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "sync_skills.py"
    rc, out = _run([_PYTHON, str(script), "--check"])
    if rc == 0:
        return GateResult("G-01", "Skill sync parity", STATUS_PASS, "sync_skills --check passed")
    return GateResult("G-01", "Skill sync parity", STATUS_FAIL, f"sync_skills --check exited {rc}: {out[:200]}")


def gate_g02_provider_sync(env: dict | None = None) -> GateResult:
    """G-02: sync_providers.py --dry-run exits 0."""
    script = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "sync_providers.py"
    rc, out = _run([_PYTHON, str(script), "--dry-run"])
    if rc == 0:
        return GateResult("G-02", "Provider sync", STATUS_PASS, "sync_providers --dry-run passed")
    return GateResult("G-02", "Provider sync", STATUS_FAIL, f"sync_providers --dry-run exited {rc}: {out[:200]}")


def gate_g03_dar_coverage(env: dict | None = None) -> GateResult:
    """G-03: check_dar_coverage.py exits 0."""
    script = _REPO_ROOT / "scripts" / "ci" / "checks" / "check_dar_coverage.py"
    rc, out = _run([_PYTHON, str(script)])
    if rc == 0:
        return GateResult("G-03", "DAR coverage", STATUS_PASS, "check_dar_coverage passed")
    lines = out.split("\n")
    summary = next((l for l in lines if l.startswith("Summary:")), out[:200])
    return GateResult("G-03", "DAR coverage", STATUS_FAIL, summary)


def gate_g04_knowledge_staleness(family: str, platform: str) -> GateResult:
    """G-04: knowledge must be fresh (FRESH-001 T7: shared freshness_guard gate,
    migrated from a raw model.yaml stale_since read). Degraded mode preserves this
    gate's prior no-network-call behavior exactly."""
    model_path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return GateResult(
            "G-04", "Knowledge staleness", STATUS_FAIL,
            f"model.yaml not found: knowledge/{family}/{platform}/merged/model.yaml",
        )
    try:
        from freshness_guard import is_generation_allowed  # noqa: PLC0415
        allowed, result = is_generation_allowed(family, platform, mode="degraded")
    except Exception as exc:
        return GateResult("G-04", "Knowledge staleness", STATUS_FAIL, f"freshness check error: {exc}")
    if allowed:
        return GateResult("G-04", "Knowledge staleness", STATUS_PASS,
                           f"state={result.state}: {result.reason}")
    return GateResult(
        "G-04", "Knowledge staleness", STATUS_FAIL,
        f"state={result.state}: {result.reason} — refresh knowledge before shipping",
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
    script = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "launch" / "launch_gate.py"
    rc, out = _run([_PYTHON, str(script), family, platform, "--skip-tests"])
    if rc == 0:
        return GateResult("G-06", "Launch gate", STATUS_PASS, f"launch_gate {family}/{platform} passed")
    lines = out.split("\n")
    fail_lines = [l for l in lines if "FAIL" in l]
    summary = "; ".join(fail_lines[:3]) if fail_lines else out[:200]
    return GateResult("G-06", "Launch gate", STATUS_FAIL, summary)


def gate_g07_cross_platform(family: str) -> GateResult:
    """G-07: cross_platform_audit.py exits 0 (no cross-platform discrepancies)."""
    script = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "content" / "cross_platform_audit.py"
    rc, out = _run([_PYTHON, str(script), family, "--json"])
    if rc == 0:
        return GateResult("G-07", "Cross-platform consistency", STATUS_PASS, f"cross_platform_audit {family}: no discrepancies")
    # rc == 1 means discrepancies found
    try:
        import json
        report = json.loads(out)
        issues = report.get("issues", [])
        issue_count = len(issues)
        if issue_count > 0:
            # Summarize first few issues
            issue_summaries = []
            for issue in issues[:3]:
                fmt = issue.get("format", "unknown")
                platforms = issue.get("platforms", {})
                detail = ", ".join(f"{p}={d}" for p, d in sorted(platforms.items()))
                issue_summaries.append(f"{fmt}: {detail}")
            summary = f"{issue_count} discrepancy(ies): {'; '.join(issue_summaries)}"
        else:
            summary = f"exit code {rc}: {out[:200]}"
    except Exception:
        summary = f"exit code {rc}: {out[:200]}"
    return GateResult("G-07", "Cross-platform consistency", STATUS_FAIL, summary)


def gate_g08_scout_fidelity(family: str, platform: str) -> GateResult:
    """G-08: scout_fidelity.py's 5 probes (TC-MT040-41 / D-2). ADVISORY ONLY
    -- this gate can never return STATUS_FAIL today (Decision 13: no probe's
    FAIL threshold may be enabled until a zero-false-positive fleet
    calibration proves it out; see scout_fidelity.PROBE_FAIL_ENABLED, all
    False at present). A findings_count > 0 result is reported as
    STATUS_WARN, never STATUS_FAIL, so this gate never contributes to
    readiness_gate.py's NOT READY verdict -- it exists to surface extraction-
    fidelity gaps for review, not to block a launch on a still-uncalibrated
    heuristic.

    Evaluated and reported completely independently of G-03 (DAR coverage):
    G-03 currently FAILs repo-wide for an unrelated, pre-existing reason
    (MT039 G5-22) -- that failure must never suppress, gate, or be conflated
    with G-08's own result, and vice versa. Each gate function in this file
    runs and reports independently; there is no cross-gate short-circuiting
    here to preserve.

    Passes --no-write-report: a readiness CHECK must not have the side
    effect of writing into knowledge/{family}/{platform}/scout/ every time
    it runs (that write only happens on scout_fidelity's normal S-54
    knowledge-bootstrap invocation, which omits this flag)."""
    script = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout_fidelity.py"
    rc, out = _run([_PYTHON, str(script), family, platform, "--json", "--no-write-report"])
    if rc not in (0, 1):
        return GateResult("G-08", "Extraction fidelity (advisory)", STATUS_SKIP,
                           f"scout_fidelity exited {rc} unexpectedly: {out[:200]}")
    try:
        report = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return GateResult("G-08", "Extraction fidelity (advisory)", STATUS_SKIP,
                           f"could not parse scout_fidelity --json output: {out[:200]}")

    findings = report.get("findings_count", 0)
    probe_statuses = report.get("probes", {})
    if findings == 0:
        clone_note = "" if report.get("clone_available") else " (no clone cache -- most probes UNAVAILABLE)"
        return GateResult("G-08", "Extraction fidelity (advisory)", STATUS_PASS,
                           f"scout_fidelity: 0 findings across {len(probe_statuses)} probes{clone_note}")
    flagged = "; ".join(
        f"{pid}={p.get('status')}: {p.get('message', '')}"
        for pid, p in probe_statuses.items() if p.get("status") in ("WARN", "FAIL")
    )
    return GateResult("G-08", "Extraction fidelity (advisory)", STATUS_WARN,
                       f"scout_fidelity: {findings} advisory finding(s) (never blocking): {flagged}"[:400])


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
    gates.append(gate_g07_cross_platform(family))
    gates.append(gate_g08_scout_fidelity(family, platform))

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
        warned = [g for g in gates if g.status == STATUS_WARN]
        print(f"VERDICT: READY — {len(passing)} gate(s) passed" +
              (f", {len(skipped)} skipped" if skipped else "") +
              (f", {len(warned)} advisory warning(s)" if warned else ""))
        return 0


if __name__ == "__main__":
    sys.exit(main())
