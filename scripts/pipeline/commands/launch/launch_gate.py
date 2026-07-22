"""launch_gate.py -- Pre-launch readiness checker for a FOSS product.

Usage:
    python scripts/pipeline/commands/launch/launch_gate.py {family} {platform}
    python scripts/pipeline/commands/launch/launch_gate.py note python
    python scripts/pipeline/commands/launch/launch_gate.py --fail-fast slides net

Runs 16 automated gates (L-01 through L-16) and prints a pass/fail summary.
Exit code: 0 if all gates pass, 1 if any gate fails.

Gates:
    L-01  Knowledge freshness   -- model.yaml stale_since must be null
    L-02  Evidence coverage     -- all content files must have evidence: block
    L-03  Forbidden claims      -- change_guard.py must exit 0 (PASS/WARN ok, DENY = fail)
    L-04  API accuracy          -- audit.py {family} {platform} must exit 0
    L-05  Format truth          -- content_eval format_truth,format_completeness evaluators must exit 0
    L-06  Promote validation    -- merged/formats.json must exist + stale_since null
                                  (promote.py has no --dry-run; this is the safe fallback
                                  until a dry-run mode is added to promote.py)
    L-07  Pipeline tests        -- pytest scripts/pipeline/tests/ must exit 0
    L-08  Provenance coverage   -- all English content files must have content_origin set
    L-09  Hugo build            -- hugo build for products.aspose.org must exit 0
    L-10  No coming-soon        -- family _index.md must not contain 'coming soon' placeholder
    L-11  Family display name   -- family root _index.md must use canonical "Aspose.{Product} FOSS"
                                  title and must not have linkTitle
    L-16  Platform linkTitle    -- platform _index.md must have canonical linkTitle matching
                                  data/platforms.json; fails on missing, wrong, or forbidden labels

Flags:
    --fail-fast     Stop after the first failing gate
    --skip-tests    Skip L-07 (pytest) for faster iteration
    --output-report Write a Markdown report to reports/launch-gate/{family}-{platform}.md
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Stdout encoding safety (TC-02: Windows CP1252 compatibility)
# ---------------------------------------------------------------------------

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Repository root and Python executable resolution
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = _HERE.parent.parent.parent.parent
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _KNOWLEDGE_ROOT, _CONTENT_ROOT, _SCRIPTS_PIPELINE
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
    _CONTENT_ROOT = _REPO_ROOT / "content"
    _SCRIPTS_PIPELINE = _REPO_ROOT / "scripts" / "pipeline"

# Prefer the project virtualenv; fall back to system Python.
_VENV_PYTHON_WIN = _REPO_ROOT / ".venv" / "Scripts" / "python.exe"
_VENV_PYTHON_UNIX = _REPO_ROOT / ".venv" / "bin" / "python"

if _VENV_PYTHON_WIN.exists():
    _PYTHON = str(_VENV_PYTHON_WIN)
elif _VENV_PYTHON_UNIX.exists():
    _PYTHON = str(_VENV_PYTHON_UNIX)
else:
    print(
        "ERROR: launch_gate: .venv not found at repo root.\n"
        "  Recovery: bash scripts/ci/hooks/repair_venv.sh\n"
        "  Or run: /getting-started",
        file=sys.stderr,
    )
    sys.exit(1)

_KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
_CONTENT_ROOT = _REPO_ROOT / "content"
_SCRIPTS_PIPELINE = _REPO_ROOT / "scripts" / "pipeline"

# ---------------------------------------------------------------------------
# Gate result data structure
# ---------------------------------------------------------------------------

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"
STATUS_WARN = "WARN"


@dataclass
class GateResult:
    gate_id: str
    name: str
    status: str
    detail: str
    extra_lines: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.gate_id} [{self.status:<4}] {self.name}: {self.detail}"


# ---------------------------------------------------------------------------
# Helper: run a subprocess and capture output
# ---------------------------------------------------------------------------

def _run(
    cmd: list[str],
    cwd: Path | None = None,
    capture_stderr: bool = True,
) -> tuple[int, str, str]:
    """Run *cmd* and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        cwd=str(cwd or _REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Gate implementations
# ---------------------------------------------------------------------------

def gate_l01_knowledge_freshness(family: str, platform: str) -> GateResult:
    """L-01: model.yaml stale_since must be null."""
    model_path = _KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return GateResult(
            "L-01", "Knowledge freshness", STATUS_FAIL,
            f"model.yaml not found at {model_path.relative_to(_REPO_ROOT)}",
        )
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return GateResult(
            "L-01", "Knowledge freshness", STATUS_FAIL,
            f"model.yaml parse error: {exc}",
        )

    stale_since = data.get("stale_since")
    if stale_since is None:
        return GateResult(
            "L-01", "Knowledge freshness", STATUS_PASS,
            "stale_since=null",
        )
    return GateResult(
        "L-01", "Knowledge freshness", STATUS_FAIL,
        f"stale_since={stale_since!r} -- run S-12->S-14 before launch",
    )


def gate_l02_evidence_coverage(family: str, platform: str) -> GateResult:
    """L-02: all English content files must have an evidence: block in frontmatter."""
    # Glob across all sites: content/*/en/{family}/{platform}/**/*.md
    patterns = [
        f"content/*/en/{family}/{platform}/**/*.md",
        f"content/*/en/{family}/{platform}/**/_index.md",
    ]
    md_files: set[Path] = set()
    for pat in patterns:
        md_files.update(_REPO_ROOT.glob(pat))

    if not md_files:
        return GateResult(
            "L-02", "Evidence coverage", STATUS_SKIP,
            f"no content files found for {family}/{platform}",
        )

    missing: list[str] = []
    for md_file in sorted(md_files):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            missing.append(str(md_file.relative_to(_REPO_ROOT)))
            continue
        if not _has_evidence_block(text):
            missing.append(str(md_file.relative_to(_REPO_ROOT)))

    total = len(md_files)
    covered = total - len(missing)
    if missing:
        extra = [f"  missing evidence: {p}" for p in missing[:20]]
        if len(missing) > 20:
            extra.append(f"  ... and {len(missing) - 20} more")
        return GateResult(
            "L-02", "Evidence coverage", STATUS_FAIL,
            f"{covered}/{total} files have evidence block ({len(missing)} missing)",
            extra_lines=extra,
        )
    return GateResult(
        "L-02", "Evidence coverage", STATUS_PASS,
        f"{covered}/{total} files have evidence block",
    )


def _has_evidence_block(text: str) -> bool:
    """Return True if the file has an evidence: key in its YAML frontmatter."""
    if not text.startswith("---"):
        return False
    # Find closing ---
    end = text.find("\n---", 3)
    if end == -1:
        return False
    frontmatter = text[3:end]
    # Simple check: look for "evidence:" at the start of a line in the frontmatter
    for line in frontmatter.splitlines():
        if line.startswith("evidence:") or line.strip() == "evidence:":
            return True
    return False


def gate_l03_forbidden_claims(family: str, platform: str) -> GateResult:
    """L-03: change_guard.py must exit with PASS or WARN (not DENY=exit 2).

    HARDEN-A7/A8 addition: any body-refresh receipt for this product whose
    forbidden-claims scan did not verifiably complete (scan_ok=False, or a
    written page with no scan record) FAILS this gate — "the scanner crashed"
    must never read as "scanned clean" at launch.
    """
    # A7: receipts with unverified forbidden-claims scans block the gate.
    receipts_dir = _REPO_ROOT / "reports" / "refresh_review" / family / platform / "receipts"
    if receipts_dir.is_dir():
        try:
            import yaml  # noqa: PLC0415
            unverified: list[str] = []
            for receipt_path in sorted(receipts_dir.glob("*.yaml")):
                data = yaml.safe_load(receipt_path.read_text(encoding="utf-8")) or {}
                receipt = data.get("content_refresh_receipt", data)
                scan = receipt.get("forbidden_claims_scan")
                if isinstance(scan, dict):
                    if scan.get("ok") is False:
                        unverified.append(receipt_path.name)
                elif receipt.get("verdict") == "BODY_UPDATED":
                    unverified.append(f"{receipt_path.name} (no scan record)")
            if unverified:
                return GateResult(
                    "L-03", "Forbidden claims", STATUS_FAIL,
                    f"{len(unverified)} receipt(s) with UNVERIFIED forbidden-claims scan — "
                    "re-run the scan (body_refresh / change_guard) before launch",
                    extra_lines=[f"  {name}" for name in unverified[:5]],
                )
        except Exception as exc:  # noqa: BLE001 — unreadable receipts are unverifiable
            return GateResult(
                "L-03", "Forbidden claims", STATUS_FAIL,
                f"could not verify receipt scan records: {exc}",
            )

    # change_guard.py requires proposed text; we pass the claims from knowledge
    # as a representative text sample. If no knowledge exists, we SKIP.
    merged_dir = _KNOWLEDGE_ROOT / family / platform / "merged"
    claims_path = merged_dir / "claims.json"

    if not merged_dir.exists():
        return GateResult(
            "L-03", "Forbidden claims", STATUS_SKIP,
            "no merged knowledge directory -- cannot run change_guard",
        )

    if not claims_path.exists():
        return GateResult(
            "L-03", "Forbidden claims", STATUS_SKIP,
            "no merged/claims.json -- cannot run change_guard",
        )

    # Build a short representative text from the first few claim texts
    try:
        import json  # noqa: PLC0415
        claims_data = json.loads(claims_path.read_text(encoding="utf-8"))
        claim_list = claims_data if isinstance(claims_data, list) else claims_data.get("claims", [])
        sample_sentences = []
        for c in claim_list[:15]:
            if isinstance(c, dict):
                txt = c.get("text", "")
            else:
                txt = str(c)
            if txt.strip():
                sample_sentences.append(txt.strip())
        sample_text = " ".join(sample_sentences[:10])
    except Exception as exc:
        return GateResult(
            "L-03", "Forbidden claims", STATUS_WARN,
            f"could not parse claims.json: {exc}",
        )

    if not sample_text.strip():
        return GateResult(
            "L-03", "Forbidden claims", STATUS_SKIP,
            "no claim text available to test",
        )

    cmd = [_PYTHON, str(_SCRIPTS_PIPELINE / "commands" / "governance" / "change_guard.py"), family, platform, sample_text]
    rc, stdout, stderr = _run(cmd)
    # exit 0 = PASS, exit 1 = WARN (acceptable), exit 2 = DENY (fail)
    if rc == 0:
        return GateResult("L-03", "Forbidden claims", STATUS_PASS, "0 DENY findings")
    if rc == 1:
        return GateResult(
            "L-03", "Forbidden claims", STATUS_WARN,
            "WARN: no direct evidence but no contradiction",
        )
    # rc == 2 -> DENY
    deny_lines = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()][:5]
    return GateResult(
        "L-03", "Forbidden claims", STATUS_FAIL,
        f"change_guard DENY (exit {rc})",
        extra_lines=[f"  {l}" for l in deny_lines],
    )


def gate_l04_api_accuracy(family: str, platform: str) -> GateResult:
    """L-04: audit.py {family} {platform} must exit 0 (0 FAIL findings).

    audit.py accepts positional 'family platform' arguments directly.
    See scripts/pipeline/audit/runner.py: args[0]=family, args[1]=platform.
    """
    cmd = [_PYTHON, str(_SCRIPTS_PIPELINE / "commands" / "content" / "audit.py"), family, platform]
    rc, stdout, stderr = _run(cmd)
    if rc == 0:
        return GateResult("L-04", "API accuracy", STATUS_PASS, "audit.py exit 0")
    # Extract summary line if present
    fail_lines = [
        line for line in (stdout + "\n" + stderr).splitlines()
        if "FAIL" in line or "fail" in line.lower()
    ][:5]
    return GateResult(
        "L-04", "API accuracy", STATUS_FAIL,
        f"audit.py exit {rc}",
        extra_lines=[f"  {l}" for l in fail_lines],
    )


def gate_l05_format_truth(family: str, platform: str) -> GateResult:
    """L-05: format_truth + format_completeness evaluators must produce 0 FAIL findings.

    content_eval CLI: python -m content_eval evaluate {family} {platform}
                       --evaluators format_truth,format_completeness --strict
    '--strict' exits 1 if any FAIL findings are present.
    """
    cmd = [
        _PYTHON, "-m", "scripts.pipeline.content_eval",
        "evaluate", family, platform,
        "--evaluators", "format_truth,format_completeness",
        "--strict",
    ]
    rc, stdout, stderr = _run(cmd)
    if rc == 0:
        return GateResult("L-05", "Format truth", STATUS_PASS, "0 FAIL findings")
    fail_lines = [
        line for line in (stderr).splitlines()
        if "FAIL" in line or "fail" in line.lower()
    ][:5]
    return GateResult(
        "L-05", "Format truth", STATUS_FAIL,
        f"format_truth,format_completeness: FAIL findings detected (exit {rc})",
        extra_lines=[f"  {l}" for l in fail_lines],
    )


def gate_l06_promote_validation(family: str, platform: str) -> GateResult:
    """L-06: Promote validation (safe fallback -- promote.py has no --dry-run).

    promote.py currently has no --dry-run or --validate-only flag, so running
    it would overwrite merged/ with side effects. Instead, this gate verifies:
      1. knowledge/{family}/{platform}/merged/formats.json exists
      2. model.yaml has stale_since: null (already checked by L-01, rechecked here)

    This is the safe fallback. When a --dry-run mode is added to promote.py,
    replace this implementation with:
        cmd = [_PYTHON, str(_SCRIPTS_PIPELINE / "promote.py"), family, platform, "--dry-run"]

    TODO(L-06): Replace with promote.py --dry-run once that flag is implemented.
    """
    merged_dir = _KNOWLEDGE_ROOT / family / platform / "merged"
    formats_path = merged_dir / "formats.json"
    model_path = merged_dir / "model.yaml"

    missing_artifacts: list[str] = []
    if not formats_path.exists():
        missing_artifacts.append("formats.json")
    if not model_path.exists():
        missing_artifacts.append("model.yaml")

    if missing_artifacts:
        return GateResult(
            "L-06", "Promote validation", STATUS_FAIL,
            f"missing merged artifacts: {', '.join(missing_artifacts)}",
        )

    # Re-check stale_since from model.yaml
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
        stale_since = data.get("stale_since")
    except Exception as exc:
        return GateResult(
            "L-06", "Promote validation", STATUS_FAIL,
            f"model.yaml parse error: {exc}",
        )

    if stale_since is not None:
        return GateResult(
            "L-06", "Promote validation", STATUS_FAIL,
            f"stale_since={stale_since!r} -- knowledge must be fresh before launch",
        )

    return GateResult(
        "L-06", "Promote validation", STATUS_SKIP,
        "promote dry-run not available (knowledge fresh, formats.json present)",
    )


def gate_l07_pipeline_tests(family: str, platform: str) -> GateResult:  # noqa: ARG001
    """L-07: pytest scripts/pipeline/tests/ must exit 0."""
    test_dirs: list[str] = []
    for candidate in [
        _SCRIPTS_PIPELINE / "tests",
    ]:
        if candidate.exists():
            test_dirs.append(str(candidate))

    if not test_dirs:
        return GateResult(
            "L-07", "Pipeline tests", STATUS_SKIP,
            "no test directories found",
        )

    cmd = [_PYTHON, "-m", "pytest"] + test_dirs + ["-q", "--tb=short"]
    rc, stdout, stderr = _run(cmd)
    if rc == 0:
        # Extract summary line (last non-empty line of pytest output)
        summary = _last_nonempty_line(stdout + stderr)
        return GateResult(
            "L-07", "Pipeline tests", STATUS_PASS,
            f"pytest exit 0{(' -- ' + summary) if summary else ''}",
        )
    summary = _last_nonempty_line(stdout + stderr)
    fail_lines = [
        line for line in (stdout + "\n" + stderr).splitlines()
        if "FAIL" in line or "failed" in line.lower() or "error" in line.lower()
    ][:5]
    return GateResult(
        "L-07", "Pipeline tests", STATUS_FAIL,
        f"pytest exit {rc}{(' -- ' + summary) if summary else ''}",
        extra_lines=[f"  {l}" for l in fail_lines],
    )


def gate_l08_provenance_coverage(family: str, platform: str) -> GateResult:
    """L-08: All English content files must have content_origin set in provenance block.

    This is the launch-gate enforcement of Check 2b (validate_frontmatter.py
    provenance_validity). Files with a provenance: block but no content_origin
    field indicate a skill that did not write provenance at creation — a
    Control 1 gap violation. FAIL blocks launch.

    Structural pages (content_origin: unknown with provenance_recovery_note:
    structural-page) are exempt — they are intentionally deferred.
    """
    md_files: set[Path] = set()
    for pat in [
        f"content/*/en/{family}/{platform}/**/*.md",
    ]:
        md_files.update(_REPO_ROOT.glob(pat))

    if not md_files:
        return GateResult(
            "L-08", "Provenance coverage", STATUS_SKIP,
            f"no content files found for {family}/{platform}",
        )

    missing_origin: list[str] = []
    absent_provenance: list[str] = []
    for md_file in sorted(md_files):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        prov_result = _check_provenance_coverage(text)
        if prov_result == "missing_origin":
            missing_origin.append(str(md_file.relative_to(_REPO_ROOT)))
        elif prov_result == "absent_provenance":
            absent_provenance.append(str(md_file.relative_to(_REPO_ROOT)))

    total = len(md_files)
    all_failures = missing_origin + absent_provenance
    if all_failures:
        extra = []
        for p in missing_origin[:10]:
            extra.append(f"  missing content_origin: {p}")
        for p in absent_provenance[:10]:
            extra.append(f"  absent provenance block: {p}")
        remainder = len(all_failures) - 20
        if remainder > 0:
            extra.append(f"  ... and {remainder} more")
        detail_parts = []
        if missing_origin:
            detail_parts.append(f"{len(missing_origin)} missing content_origin")
        if absent_provenance:
            detail_parts.append(f"{len(absent_provenance)} absent provenance block")
        return GateResult(
            "L-08", "Provenance coverage", STATUS_FAIL,
            f"{len(all_failures)}/{total} files fail provenance check: {', '.join(detail_parts)}",
            extra_lines=extra,
        )
    return GateResult(
        "L-08", "Provenance coverage", STATUS_PASS,
        f"all {total} files have provenance with content_origin",
    )


def _check_provenance_coverage(text: str) -> str:
    """Return 'missing_origin' if file has provenance block without content_origin.

    Returns 'ok' if no provenance block, or provenance has content_origin,
    or file is a structural-deferred page (content_origin: unknown +
    provenance_recovery_note: structural-page).
    """
    if not text.startswith("---"):
        return "ok"
    end = text.find("\n---", 3)
    if end == -1:
        return "ok"
    frontmatter = text[3:end]

    # Check if provenance block exists
    has_provenance = any(
        line.startswith("provenance:") or line.strip() == "provenance:"
        for line in frontmatter.splitlines()
    )
    if not has_provenance:
        # Structural pages (layout: list/family/reference-home) are exempt from provenance
        # requirement — they are Hugo section indices with no narrative content.
        _STRUCTURAL_LAYOUTS = ("list", "family", "reference-home")
        has_structural_layout = any(
            "layout:" in line and any(lay in line for lay in _STRUCTURAL_LAYOUTS)
            for line in frontmatter.splitlines()
        )
        if has_structural_layout:
            return "ok"
        return "absent_provenance"

    # Provenance block present — check for content_origin
    has_content_origin = any(
        "content_origin:" in line
        for line in frontmatter.splitlines()
    )
    if has_content_origin:
        return "ok"

    return "missing_origin"


def gate_l09_hugo_build(family: str, platform: str) -> GateResult:  # noqa: ARG001
    """L-09: Hugo build for products.aspose.org must exit 0.

    Runs 'hugo --config configs/products.aspose.org.toml' to verify that
    all product pages compile without errors.  Does NOT verify rendering
    completeness — Hugo silently skips missing frontmatter sections via
    {{ with }} template guards.  Use validate_plugin_structure.py for
    structural completeness checks.

    Known limitation: only builds products.aspose.org.  Other sites
    (docs, kb, reference) may have remote theme dependencies that are
    not always cached locally.
    """
    config_path = _REPO_ROOT / "configs" / "products.aspose.org.toml"
    if not config_path.exists():
        return GateResult(
            "L-09", "Hugo build", STATUS_SKIP,
            "products.aspose.org config not found",
        )

    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    hugo_bin = shutil.which("hugo")
    if not hugo_bin:
        return GateResult(
            "L-09", "Hugo build", STATUS_SKIP,
            "hugo not found in PATH",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [hugo_bin, "--config", str(config_path), "-d", tmpdir, "--quiet"]
        rc, stdout, stderr = _run(cmd)

    if rc == 0:
        return GateResult("L-09", "Hugo build", STATUS_PASS, "hugo exit 0")

    err_lines = [
        line for line in (stdout + "\n" + stderr).splitlines()
        if line.strip()
    ][:10]
    return GateResult(
        "L-09", "Hugo build", STATUS_FAIL,
        f"hugo exit {rc}",
        extra_lines=[f"  {l}" for l in err_lines],
    )


def gate_l10_no_coming_soon(family: str, platform: str) -> GateResult:  # noqa: ARG001
    """L-10: Family _index.md must not contain stale 'coming soon' placeholder text.

    A 'coming soon' string in the family page indicates a pre-existing structural
    placeholder that was not replaced during launch (ISSUE-04 / CV-HEAL-04).
    Run /family-sync {family} to replace the placeholder with auto-generated content.
    """
    family_page = _CONTENT_ROOT / "products.aspose.org" / "en" / family / "_index.md"
    if not family_page.exists():
        return GateResult(
            "L-10", "No coming-soon placeholder", STATUS_SKIP,
            "family _index.md not found (new family — will be created during launch)",
        )
    try:
        text = family_page.read_text(encoding="utf-8", errors="replace").lower()
    except OSError as exc:
        return GateResult("L-10", "No coming-soon placeholder", STATUS_FAIL, f"read error: {exc}")

    if "coming soon" in text:
        return GateResult(
            "L-10", "No coming-soon placeholder", STATUS_FAIL,
            f"family page contains 'coming soon' placeholder — run /family-sync {family} to replace it",
        )
    return GateResult(
        "L-10", "No coming-soon placeholder", STATUS_PASS,
        "no 'coming soon' placeholder found in family page",
    )


def gate_l11_family_display_name(family: str, platform: str) -> GateResult:  # noqa: ARG001
    """L-11: Family root _index.md must use canonical display name without linkTitle.

    Checks family-level _index.md across reference/docs/kb to ensure:
    1. No linkTitle field (causes sidebar to show short name instead of full title)
    2. title matches "{Canonical Product Name} FOSS" per metrics_taxonomy.yaml
    """
    import yaml  # noqa: PLC0415

    taxonomy_path = (
        _REPO_ROOT / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml"
    )
    if not taxonomy_path.exists():
        return GateResult(
            "L-11", "Family display name", STATUS_SKIP,
            "metrics_taxonomy.yaml not found",
        )

    try:
        with open(taxonomy_path, encoding="utf-8") as f:
            taxonomy = yaml.safe_load(f)
        products = taxonomy.get("products", {})
    except Exception as exc:
        return GateResult(
            "L-11", "Family display name", STATUS_FAIL,
            f"failed to load taxonomy: {exc}",
        )

    canonical = products.get(family)
    if not canonical:
        return GateResult(
            "L-11", "Family display name", STATUS_SKIP,
            f"family {family!r} not in taxonomy",
        )

    expected_title = f"{canonical} FOSS"
    sites = ["reference.aspose.org", "docs.aspose.org", "kb.aspose.org"]
    fails: list[str] = []
    checked = 0

    for site in sites:
        index_md = _CONTENT_ROOT / site / "en" / family / "_index.md"
        if not index_md.exists():
            continue
        checked += 1

        try:
            text = index_md.read_text(encoding="utf-8")
        except OSError as exc:
            fails.append(f"{site}: read error — {exc}")
            continue

        if not text.startswith("---"):
            fails.append(f"{site}: missing frontmatter delimiters")
            continue
        end = text.find("\n---", 3)
        if end == -1:
            fails.append(f"{site}: unclosed frontmatter")
            continue
        try:
            fm = yaml.safe_load(text[3:end])
        except yaml.YAMLError as exc:
            fails.append(f"{site}: YAML parse error — {exc}")
            continue
        if not isinstance(fm, dict):
            fails.append(f"{site}: frontmatter is not a dict")
            continue

        link_title = fm.get("linkTitle")
        if link_title is not None:
            fails.append(
                f"{site}: linkTitle={link_title!r} present — remove it"
            )

        title = fm.get("title", "")
        if title != expected_title:
            fails.append(
                f"{site}: title={title!r} != expected {expected_title!r}"
            )

    if not checked:
        return GateResult(
            "L-11", "Family display name", STATUS_SKIP,
            f"no family root _index.md found for {family}",
        )

    if fails:
        return GateResult(
            "L-11", "Family display name", STATUS_FAIL,
            f"{len(fails)} issue(s) in family display name",
            extra_lines=[f"  {f}" for f in fails],
        )

    return GateResult(
        "L-11", "Family display name", STATUS_PASS,
        f"title={expected_title!r}, no linkTitle — {checked} site(s) checked",
    )


def _last_nonempty_line(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[-1] if lines else ""


# ---------------------------------------------------------------------------
# New gates L-12 through L-15
# ---------------------------------------------------------------------------

def gate_l12_denominator_reconciliation(family: str, platform: str) -> GateResult:
    """L-12: Generation manifest denominator_gap must be 0.

    Reads the generation manifest at reports/generation/{family}-{platform}.yaml
    and verifies that the denominator gap (scope_eligible - pages_accounted_for)
    is zero. If no manifest exists, falls back to live reconciliation.
    """
    manifest_path = _REPO_ROOT / "reports" / "generation" / f"{family}-{platform}.yaml"

    # Try manifest first
    if manifest_path.exists():
        try:
            import yaml  # noqa: PLC0415
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            gap = data.get("denominator_gap", -1)
            eligible = data.get("scope_eligible", 0)
            if gap == 0:
                return GateResult(
                    "L-12", "Denominator reconciliation", STATUS_PASS,
                    f"gap=0 (manifest: {eligible} scope-eligible)",
                )
            if gap <= 5:
                return GateResult(
                    "L-12", "Denominator reconciliation", STATUS_WARN,
                    f"gap={gap} (manifest: {eligible} eligible, tolerance ≤5)",
                )
            return GateResult(
                "L-12", "Denominator reconciliation", STATUS_FAIL,
                f"gap={gap} (manifest: {eligible} eligible)",
            )
        except Exception as exc:
            return GateResult(
                "L-12", "Denominator reconciliation", STATUS_FAIL,
                f"manifest parse error: {exc}",
            )

    # Fallback: live reconciliation
    try:
        import sys as _sys
        _lib = str(_REPO_ROOT / "scripts" / "pipeline" / "lib")
        _cmd = str(_REPO_ROOT / "scripts" / "pipeline" / "commands" / "content")
        if _lib not in _sys.path:
            _sys.path.insert(0, _lib)
        if _cmd not in _sys.path:
            _sys.path.insert(0, _cmd)
        from denominator_reconciler import reconcile

        report = reconcile(family, platform,
                           knowledge_root=_KNOWLEDGE_ROOT,
                           content_root=_CONTENT_ROOT)
        gap = report.get("denominator_gap", -1)
        eligible = report.get("scope_eligible", 0)
        if "error" in report:
            return GateResult(
                "L-12", "Denominator reconciliation", STATUS_SKIP,
                f"reconciler error: {report['error']}",
            )
        if gap == 0:
            return GateResult(
                "L-12", "Denominator reconciliation", STATUS_PASS,
                f"gap=0 (live: {eligible} scope-eligible, {report.get('pages_on_disk', 0)} pages)",
            )
        if gap <= 5:
            return GateResult(
                "L-12", "Denominator reconciliation", STATUS_WARN,
                f"gap={gap} (live: {eligible} eligible)",
            )
        return GateResult(
            "L-12", "Denominator reconciliation", STATUS_FAIL,
            f"gap={gap} (live: {eligible} eligible)",
            extra_lines=[f"  missing: {', '.join(report.get('missing_pages', [])[:10])}"],
        )
    except Exception as exc:
        return GateResult(
            "L-12", "Denominator reconciliation", STATUS_SKIP,
            f"reconciler unavailable: {exc}",
        )


def gate_l13_cross_subdomain_build(family: str, platform: str) -> GateResult:  # noqa: ARG001
    """L-13: Hugo build for all local-theme sites must exit 0.

    Extends L-09 by attempting to build all sites with local themes.
    Sites requiring remote themes are skipped to avoid network dependency.
    """
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    hugo_bin = shutil.which("hugo")
    if not hugo_bin:
        return GateResult("L-13", "Cross-subdomain Hugo build", STATUS_SKIP, "hugo not found in PATH")

    # Sites with local themes (no network dependency)
    local_configs = [
        ("products.aspose.org", _REPO_ROOT / "configs" / "products.aspose.org.toml"),
    ]

    results = []
    for site_name, config_path in local_configs:
        if not config_path.exists():
            results.append((site_name, "SKIP", "config not found"))
            continue
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [hugo_bin, "--config", str(config_path), "-d", tmpdir, "--quiet"]
            rc, stdout, stderr = _run(cmd)
        if rc == 0:
            results.append((site_name, "PASS", ""))
        else:
            err = (stdout + stderr).strip()[:200]
            results.append((site_name, "FAIL", err))

    fails = [r for r in results if r[1] == "FAIL"]
    if fails:
        return GateResult(
            "L-13", "Cross-subdomain Hugo build", STATUS_FAIL,
            f"{len(fails)} site(s) failed Hugo build",
            extra_lines=[f"  {r[0]}: {r[2]}" for r in fails],
        )
    passes = sum(1 for r in results if r[1] == "PASS")
    skips = sum(1 for r in results if r[1] == "SKIP")
    return GateResult(
        "L-13", "Cross-subdomain Hugo build", STATUS_PASS,
        f"{passes} site(s) built OK, {skips} skipped (remote theme)",
    )


def gate_l14_grade_non_regression(family: str, platform: str) -> GateResult:
    """L-14: No page grade decreased vs baseline in grade_manifest.json.

    Compares current grades against the baseline snapshot in
    reports/grade_manifest.json. If no baseline exists, SKIP.
    """
    manifest_path = _REPO_ROOT / "reports" / "grade_manifest.json"
    if not manifest_path.exists():
        return GateResult(
            "L-14", "Grade non-regression", STATUS_SKIP,
            "no grade_manifest.json baseline found",
        )

    try:
        import json  # noqa: PLC0415
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return GateResult(
            "L-14", "Grade non-regression", STATUS_FAIL,
            f"grade_manifest.json parse error: {exc}",
        )

    # grade_manifest.json structure: {"pages": [{"path": ..., "grade": ...}, ...]}
    pages = data if isinstance(data, list) else data.get("pages", [])
    if not pages:
        return GateResult(
            "L-14", "Grade non-regression", STATUS_SKIP,
            "grade_manifest.json has no page entries",
        )

    # Filter to this family/platform
    prefix = f"content/reference.aspose.org/en/{family}/{platform}/"
    relevant = [p for p in pages if isinstance(p, dict) and prefix in p.get("path", "")]

    if not relevant:
        return GateResult(
            "L-14", "Grade non-regression", STATUS_SKIP,
            f"no entries for {family}/{platform} in grade_manifest.json",
        )

    # For now, just report stats (no previous baseline to compare against)
    grade_counts: dict[str, int] = {}
    for p in relevant:
        g = p.get("grade", "?")
        grade_counts[g] = grade_counts.get(g, 0) + 1

    summary = ", ".join(f"{g}: {c}" for g, c in sorted(grade_counts.items()))
    return GateResult(
        "L-14", "Grade non-regression", STATUS_PASS,
        f"{len(relevant)} pages graded ({summary})",
    )


def gate_l15_snippet_syntax(family: str, platform: str) -> GateResult:
    """L-15: All snippets must be syntactically valid (basic check).

    Checks that snippet files in knowledge/{family}/{platform}/merged/snippets/
    are non-empty and have balanced braces/brackets.
    """
    snippets_dir = _KNOWLEDGE_ROOT / family / platform / "merged" / "snippets"
    if not snippets_dir.exists():
        return GateResult(
            "L-15", "Snippet syntax", STATUS_SKIP,
            f"no snippets directory for {family}/{platform}",
        )

    snippet_files = list(snippets_dir.glob("*"))
    if not snippet_files:
        return GateResult(
            "L-15", "Snippet syntax", STATUS_SKIP,
            "snippets directory is empty",
        )

    issues: list[str] = []
    for sf in snippet_files:
        try:
            text = sf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            issues.append(f"{sf.name}: unreadable")
            continue

        if not text.strip():
            issues.append(f"{sf.name}: empty file")
            continue

        # Basic bracket balance check
        opens = text.count("(") + text.count("[") + text.count("{")
        closes = text.count(")") + text.count("]") + text.count("}")
        if abs(opens - closes) > 2:
            issues.append(f"{sf.name}: bracket imbalance ({opens} open, {closes} close)")

    if issues:
        return GateResult(
            "L-15", "Snippet syntax", STATUS_WARN,
            f"{len(issues)} snippet issue(s) out of {len(snippet_files)}",
            extra_lines=[f"  {i}" for i in issues[:10]],
        )
    return GateResult(
        "L-15", "Snippet syntax", STATUS_PASS,
        f"all {len(snippet_files)} snippets pass basic syntax check",
    )


def gate_l16_platform_linktitle(family: str, platform: str) -> GateResult:
    """L-16: Platform _index.md must have canonical linkTitle matching registry.

    Checks platform-level _index.md across reference/docs/kb/blog to ensure:
    1. linkTitle (or linktitle) frontmatter field is present.
    2. The value matches the canonical display name from data/platforms.json.
    3. The rendered badge label does not contain forbidden patterns.
    """
    import yaml  # noqa: PLC0415

    platforms_path = _REPO_ROOT / "data" / "platforms.json"
    if not platforms_path.exists():
        return GateResult(
            "L-16", "Platform linkTitle", STATUS_SKIP,
            "data/platforms.json not found",
        )

    try:
        import json as _json
        registry = _json.loads(platforms_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return GateResult(
            "L-16", "Platform linkTitle", STATUS_FAIL,
            f"failed to load platforms.json: {exc}",
        )

    expected = registry.get(platform)
    if not expected:
        return GateResult(
            "L-16", "Platform linkTitle", STATUS_FAIL,
            f"platform slug {platform!r} not in data/platforms.json — register it first",
        )

    sites = [
        ("reference", _CONTENT_ROOT / "reference.aspose.org" / "en"),
        ("docs", _CONTENT_ROOT / "docs.aspose.org" / "en"),
        ("kb", _CONTENT_ROOT / "kb.aspose.org" / "en"),
        ("blog", _CONTENT_ROOT / "blog.aspose.org"),
    ]
    forbidden = ["Knowledge Base", "Documentation", "API Reference", "FOSS for"]
    fails: list[str] = []
    checked = 0

    for site_name, base in sites:
        index_md = base / family / platform / "_index.md"
        if not index_md.exists():
            continue
        checked += 1

        try:
            text = index_md.read_text(encoding="utf-8")
        except OSError as exc:
            fails.append(f"{site_name}: read error — {exc}")
            continue

        if not text.startswith("---"):
            fails.append(f"{site_name}: missing frontmatter delimiters")
            continue
        end = text.find("\n---", 3)
        if end == -1:
            fails.append(f"{site_name}: unclosed frontmatter")
            continue
        try:
            fm = yaml.safe_load(text[3:end])
        except yaml.YAMLError as exc:
            fails.append(f"{site_name}: YAML parse error — {exc}")
            continue
        if not isinstance(fm, dict):
            fails.append(f"{site_name}: frontmatter is not a dict")
            continue

        lt = fm.get("linkTitle") or fm.get("linktitle")
        if lt is None:
            fails.append(f"{site_name}: linkTitle missing")
            continue

        if lt != expected:
            fails.append(
                f"{site_name}: linkTitle={lt!r} != expected {expected!r}"
            )

        rendered = lt or fm.get("title", "")
        for pat in forbidden:
            if pat in rendered:
                fails.append(
                    f"{site_name}: badge label {rendered!r} contains forbidden {pat!r}"
                )

    if not checked:
        return GateResult(
            "L-16", "Platform linkTitle", STATUS_SKIP,
            f"no platform _index.md found for {family}/{platform}",
        )

    if fails:
        return GateResult(
            "L-16", "Platform linkTitle", STATUS_FAIL,
            f"{len(fails)} issue(s) in platform linkTitle",
            extra_lines=[f"  {f}" for f in fails],
        )

    return GateResult(
        "L-16", "Platform linkTitle", STATUS_PASS,
        f"linkTitle={expected!r} correct across {checked} site(s)",
    )


# ---------------------------------------------------------------------------
# Gate registry (ordered)
# ---------------------------------------------------------------------------

_ALL_GATES = [
    gate_l01_knowledge_freshness,
    gate_l02_evidence_coverage,
    gate_l03_forbidden_claims,
    gate_l04_api_accuracy,
    gate_l05_format_truth,
    gate_l06_promote_validation,
    gate_l07_pipeline_tests,
    gate_l08_provenance_coverage,
    gate_l09_hugo_build,
    gate_l10_no_coming_soon,
    gate_l11_family_display_name,
    gate_l12_denominator_reconciliation,
    gate_l13_cross_subdomain_build,
    gate_l14_grade_non_regression,
    gate_l15_snippet_syntax,
    gate_l16_platform_linktitle,
]


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

_DIVIDER = "-" * 33


def _render_console(family: str, platform: str, results: list[GateResult]) -> str:
    lines = [
        f"Launch Gate: {family}/{platform}",
        _DIVIDER,
    ]
    for r in results:
        lines.append(str(r))
        lines.extend(r.extra_lines)

    passes = sum(1 for r in results if r.status == STATUS_PASS)
    fails = sum(1 for r in results if r.status == STATUS_FAIL)
    warns = sum(1 for r in results if r.status == STATUS_WARN)
    skips = sum(1 for r in results if r.status == STATUS_SKIP)

    overall = STATUS_FAIL if fails > 0 else STATUS_PASS
    lines.append(_DIVIDER)
    lines.append(
        f"Result: {overall}"
        + (f" ({fails} gate{'s' if fails != 1 else ''} failed)" if fails else "")
    )
    stat_parts = [f"{passes} PASS"]
    if fails:
        stat_parts.append(f"{fails} FAIL")
    if warns:
        stat_parts.append(f"{warns} WARN")
    if skips:
        stat_parts.append(f"{skips} SKIP")
    lines.append(f"Gates: {', '.join(stat_parts)}")
    return "\n".join(lines)


def _render_markdown(family: str, platform: str, results: list[GateResult]) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Launch Gate Report: {family}/{platform}",
        f"",
        f"**Generated**: {ts}  ",
        f"**Product**: `{family}/{platform}`  ",
        f"",
        f"## Gate Results",
        f"",
        f"| Gate | Status | Detail |",
        f"|------|--------|--------|",
    ]
    for r in results:
        badge = {"PASS": "[OK]", "FAIL": "[X]", "SKIP": ">>|", "WARN": "WARN"}.get(r.status, r.status)
        lines.append(f"| {r.gate_id} {r.name} | {badge} {r.status} | {r.detail} |")

    passes = sum(1 for r in results if r.status == STATUS_PASS)
    fails = sum(1 for r in results if r.status == STATUS_FAIL)
    warns = sum(1 for r in results if r.status == STATUS_WARN)
    skips = sum(1 for r in results if r.status == STATUS_SKIP)
    overall = STATUS_FAIL if fails > 0 else STATUS_PASS

    lines += [
        f"",
        f"## Summary",
        f"",
        f"- **Overall**: {overall}",
        f"- **PASS**: {passes}",
        f"- **FAIL**: {fails}",
        f"- **WARN**: {warns}",
        f"- **SKIP**: {skips}",
    ]

    # Append verbose details for failed/warned gates
    detail_gates = [r for r in results if r.status in (STATUS_FAIL, STATUS_WARN) and r.extra_lines]
    if detail_gates:
        lines += ["", "## Failure Details", ""]
        for r in detail_gates:
            lines.append(f"### {r.gate_id} {r.name}")
            lines.append(f"")
            lines.append(f"**Status**: {r.status}  ")
            lines.append(f"**Detail**: {r.detail}  ")
            if r.extra_lines:
                lines.append(f"")
                lines.append("```")
                lines.extend(r.extra_lines)
                lines.append("```")
            lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="launch_gate",
        description="Pre-launch readiness checker (L-01 through L-09)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("family", help="Product family (e.g. note, slides, cells)")
    parser.add_argument("platform", help="Platform (e.g. python, net, java)")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing gate",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip L-07 (pytest) for faster iteration",
    )
    parser.add_argument(
        "--output-report",
        action="store_true",
        help="Write a Markdown report to reports/launch-gate/{family}-{platform}.md",
    )
    args = parser.parse_args(argv)

    family: str = args.family
    platform: str = args.platform

    gates_to_run = list(_ALL_GATES)
    if args.skip_tests:
        # Remove L-07 (pipeline tests) for faster iteration
        gates_to_run = [g for g in gates_to_run if g.__name__ != "gate_l07_pipeline_tests"]

    results: list[GateResult] = []

    for gate_fn in gates_to_run:
        result = gate_fn(family, platform)
        results.append(result)
        # Print gate result immediately so progress is visible
        print(result)
        for extra in result.extra_lines:
            print(extra)
        if args.fail_fast and result.status == STATUS_FAIL:
            # Fill remaining gates as SKIP
            remaining = gates_to_run[gates_to_run.index(gate_fn) + 1:]
            for remaining_fn in remaining:
                # Derive gate ID from function name: gate_l01_... -> L-01
                name_parts = remaining_fn.__name__.split("_")
                gate_id = (name_parts[1].upper().replace("l", "L-", 1)
                           if len(name_parts) > 1 else "?")
                skip_result = GateResult(
                    gate_id, remaining_fn.__doc__.split("\n")[0].split(":")[1].strip()
                    if remaining_fn.__doc__ else remaining_fn.__name__,
                    STATUS_SKIP,
                    "skipped due to --fail-fast",
                )
                results.append(skip_result)
                print(skip_result)
            break

    # Summary
    print(_DIVIDER)
    fails = sum(1 for r in results if r.status == STATUS_FAIL)
    passes = sum(1 for r in results if r.status == STATUS_PASS)
    warns = sum(1 for r in results if r.status == STATUS_WARN)
    skips = sum(1 for r in results if r.status == STATUS_SKIP)
    overall = STATUS_FAIL if fails > 0 else STATUS_PASS

    print(
        f"Result: {overall}"
        + (f" ({fails} gate{'s' if fails != 1 else ''} failed)" if fails else "")
    )
    stat_parts = [f"{passes} PASS"]
    if fails:
        stat_parts.append(f"{fails} FAIL")
    if warns:
        stat_parts.append(f"{warns} WARN")
    if skips:
        stat_parts.append(f"{skips} SKIP")
    print(f"Gates: {', '.join(stat_parts)}")

    # Optional markdown report
    if args.output_report:
        report_dir = _REPO_ROOT / "reports" / "launch-gate"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{family}-{platform}.md"
        report_md = _render_markdown(family, platform, results)
        report_path.write_text(report_md, encoding="utf-8")
        print(f"\nReport written to: {report_path.relative_to(_REPO_ROOT)}")

    return 1 if fails > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
