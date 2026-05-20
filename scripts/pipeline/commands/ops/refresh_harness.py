# Adapted from aspose.org
"""refresh_harness.py — TC-PROD-006: Forced validation harness for the refresh architecture.

Runs the refresh decision engine against real or synthetic state and produces
reconciliation evidence. Writes NO content (all outputs go to scratch root or shadow paths).

Modes:
  dry-run        Collect fingerprints and decisions only. No writes of any kind.
  validate-only  Run validators on existing content. No content writes.
  force-reconcile Ignore stored manifests. Check all expected vs actual outputs.
  synthetic-input-change Inject in-memory fingerprint overrides. Production files untouched.

Safety rules:
  - Never writes to content/
  - --scratch-root is required for any mode that produces output files
  - --no-write is the default (must pass --allow-write to override)
  - Synthetic overrides are run-context-only (in-memory, never on disk)
  - If --restore-after is used and restore verification fails: status = BLOCKED

Usage:
  python scripts/pipeline/commands/ops/refresh_harness.py \\
    --product cells/java \\
    --mode dry-run \\
    --scratch-root runs/harness-scratch/run001

  python scripts/pipeline/commands/ops/refresh_harness.py \\
    --product cells/java \\
    --mode synthetic-input-change \\
    --fingerprint upstream_repo_sha=SYNTHETIC_TC108 \\
    --triage-case TC-108 \\
    --scratch-root runs/harness-scratch/tc108 \\
    --no-write

Exit codes:
  0  success (PASS or DRY_RUN_PASS)
  1  failure (FAIL or BLOCKED)
  2  configuration error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from decision_engine import OutputState, decide
from dependency_registry import load_registry
from freshness_manifest import FreshnessManifest, load as load_manifest, validate_for_fresh
from reconciliation_ledger import (
    BLOCKED,
    DRY_RUN_PASS,
    FAIL,
    PASS,
    SurfaceRecord,
    build_ledger,
    load_tc_closure_conditions,
)

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))

_VALID_MODES = frozenset({"dry-run", "validate-only", "force-reconcile", "synthetic-input-change"})

_REGISTRY_PATH = _REPO_ROOT / "data" / "refresh-dependencies.json"
_FEATURE_FLAGS_PATH = _REPO_ROOT / "data" / "refresh-feature-flags.json"


# ---------------------------------------------------------------------------
# Feature flag loader
# ---------------------------------------------------------------------------

def load_feature_flags(path: Path = _FEATURE_FLAGS_PATH) -> dict:
    """Load refresh feature flags. Returns safe defaults if file is missing."""
    defaults = {
        "refresh_decision_engine_enabled": False,
        "refresh_decision_engine_shadow": True,
        "refresh_reconciliation_shadow": True,
        "refresh_reconciliation_enforced": False,
        "refresh_manifest_write_enabled": False,
        "refresh_content_write_enabled": False,
        "refresh_run_type_label_enabled": True,
    }
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        defaults.update(data)
        return defaults
    except (OSError, json.JSONDecodeError):
        return defaults


# ---------------------------------------------------------------------------
# Fingerprint collection helper (thin wrapper)
# ---------------------------------------------------------------------------

def _collect_fingerprints_with_overrides(
    product: str,
    subdomain: str,
    registry,
    synthetic_overrides: dict,
) -> dict:
    """Collect real fingerprints and apply in-memory synthetic overrides.

    Synthetic overrides are NEVER written to disk. They exist only in the
    returned dict for this run.

    TC-HEAL-003: Collection errors are now logged to stderr and surfaced in the
    returned dict under the key "_collection_errors" (a list of strings).
    Callers should surface this in the ledger record explanation when non-empty.
    The bare except Exception has been replaced with a specific handler that
    preserves errors instead of silently swallowing them.

    Args:
        product: Product slug "family/platform".
        subdomain: Surface name.
        registry: Loaded DependencyRegistry.
        synthetic_overrides: Dict of fingerprint_name -> override_value.
            Applied after collection; production files are not touched.

    Returns:
        Dict of fingerprint name -> value, plus "_collection_errors" key if any.
    """
    import sys as _sys
    collection_errors = []
    try:
        try:
            from fingerprint_collector import collect_input_fingerprints
        except ImportError:
            collection_errors.append("fingerprint_collector not available in foss")
            return fingerprints
        fp_set = collect_input_fingerprints(product, subdomain, registry)
        fingerprints = fp_set.to_dict()
        if fp_set.collection_errors:
            collection_errors.extend(fp_set.collection_errors)
    except Exception as exc:
        collection_errors.append(f"fingerprint collection failed: {exc}")
        fingerprints = {}

    if collection_errors:
        print(
            f"HARNESS WARN [{product}/{subdomain}]: fingerprint collection errors: "
            + "; ".join(collection_errors),
            file=_sys.stderr,
        )
        fingerprints["_collection_errors"] = collection_errors

    # Apply synthetic overrides in memory only
    fingerprints.update(synthetic_overrides)
    # Remove internal key before returning if override added it
    fingerprints.pop("_collection_errors", None)
    if collection_errors:
        fingerprints["_collection_errors"] = collection_errors
    return fingerprints


# ---------------------------------------------------------------------------
# Output state inspector
# ---------------------------------------------------------------------------

def _inspect_output_state(product: str, subdomain: str, registry) -> OutputState:
    """Inspect current on-disk output state for (product, subdomain).

    Returns OutputState including output_content_hash when content exists.
    The hash is computed live via compute_output_content_hash() so that
    validate_for_fresh() can verify content integrity.
    """
    try:
        surface = registry.get_surface(subdomain)
        content_root_template = surface.content_root
        if not content_root_template:
            return OutputState(output_exists=False)

        # Resolve template: split product into family/platform
        parts = product.split("/", 1)
        if len(parts) != 2:
            return OutputState(output_exists=False)
        family, platform = parts

        content_root = content_root_template.format(family=family, platform=platform)
        content_path = _REPO_ROOT / content_root
        output_exists = content_path.is_dir() and any(content_path.rglob("*.md"))

        output_hash = None
        if output_exists:
            from freshness_manifest import compute_output_content_hash
            output_hash = compute_output_content_hash(content_path)

        return OutputState(output_exists=output_exists, output_content_hash=output_hash)
    except Exception:
        return OutputState(output_exists=False)


# ---------------------------------------------------------------------------
# Gate 3a: Manifest write helpers
# ---------------------------------------------------------------------------

_STATE_ROOT = _REPO_ROOT / "runs" / "state"


def _restore_backup(manifest_path: Path, backup_path: Path) -> None:
    """Restore manifest from pre-Gate-3 backup using os.replace.

    Called on manifest write failure to ensure the manifest directory
    is left in a known-good state.
    """
    import sys as _sys
    if backup_path.is_file():
        try:
            import os as _os
            _os.replace(str(backup_path), str(manifest_path))
            print(
                f"[GATE3-RESTORE] Backup restored to {manifest_path}",
                file=_sys.stderr,
            )
        except OSError as exc:
            print(
                f"[GATE3-RESTORE-FAIL] Could not restore backup: {exc}",
                file=_sys.stderr,
            )
    else:
        print(
            f"[GATE3-RESTORE-WARN] No backup found at {backup_path}",
            file=_sys.stderr,
        )


def _write_manifest_gated(
    product: str,
    subdomain: str,
    fingerprints: dict,
    current_outputs: OutputState,
    stored: FreshnessManifest,
    run_id: str,
    flags: dict,
    no_write: bool,
    state_root: Optional[Path] = None,
) -> "tuple[bool, str]":
    """Attempt a gated manifest write after a confirmed FRESH decision.

    Gate 3a: Writes an updated freshness manifest only when all safety conditions
    are satisfied. Creates a pre-write backup and verifies the written file.
    Restores the backup on any failure.

    Pre-conditions (caller must ensure):
      - d.decision == "FRESH"
      - validate_for_fresh() returned [] (no violations)
      - refresh_content_write_enabled == False (hard-blocked by caller too)

    Args:
        product: Product slug "family/platform".
        subdomain: Surface name.
        fingerprints: Current input fingerprints (without _collection_errors).
        current_outputs: Current output state.
        stored: The existing FRESH manifest on disk (base for update).
        run_id: Current run identifier.
        flags: Feature flags dict (from load_feature_flags()).
        no_write: If True, no write is performed regardless of flags.
        state_root: Override for manifest state directory (for testing).

    Returns:
        (written: bool, note: str) where:
          written=True  -> manifest written and verified successfully
          written=False -> skipped (note explains why) or FAILED (note contains "FAILED")

    Raises:
        RuntimeError: If refresh_content_write_enabled=True (HARD_BLOCK).
    """
    import sys as _sys
    import datetime
    import shutil
    from freshness_manifest import FreshnessManifest as _FM
    from freshness_manifest import save as _fm_save
    from freshness_manifest import load as _fm_load

    effective_state_root: Path = state_root if state_root is not None else _STATE_ROOT

    # HARD_BLOCK: content writes are never permitted — defense-in-depth (caller also checks).
    if flags.get("refresh_content_write_enabled", False):
        raise RuntimeError(
            "HARD_BLOCK: refresh_content_write_enabled=True is not permitted. "
            "This flag must remain false throughout Gate 3."
        )

    # Guard: manifest write flag must be enabled.
    if not flags.get("refresh_manifest_write_enabled", False):
        return False, "manifest write skipped (refresh_manifest_write_enabled=False)"

    # Guard: enforced mode must be active.
    if not flags.get("refresh_reconciliation_enforced", False):
        return False, "manifest write skipped (refresh_reconciliation_enforced=False)"

    # Guard: no_write must be off.
    if no_write:
        return False, "manifest write skipped (no_write=True)"

    # Guard: must have an existing manifest to update.
    if stored is None:
        return False, "manifest write skipped (no stored manifest)"

    # Resolve manifest and backup paths.
    family, platform = product.split("/", 1)
    manifest_dir = effective_state_root / family / platform / subdomain
    manifest_path = manifest_dir / "freshness-manifest.json"
    backup_path = manifest_dir / "freshness-manifest.pre-gate3.json"

    if not manifest_path.is_file():
        return False, "manifest write skipped (manifest file not on disk)"

    # Create pre-write backup (only if not already present from a prior interrupted run).
    if backup_path.exists():
        print(
            f"[GATE3-WARN] Pre-write backup already exists at {backup_path}. "
            "Using existing backup (may indicate a prior interrupted run).",
            file=_sys.stderr,
        )
    else:
        shutil.copy2(str(manifest_path), str(backup_path))
        print(f"[GATE3] Pre-write backup created: {backup_path}", file=_sys.stderr)

    # Build updated manifest from stored baseline.
    now_ts = (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    data = stored.to_dict()
    data["manifest_status"] = "FRESH"
    data["run_id"] = run_id
    data["generation_timestamp"] = now_ts
    data["input_fingerprints"] = {
        k: v for k, v in fingerprints.items() if not k.startswith("_")
    }
    data["changed_input_fingerprints"] = []
    if current_outputs is not None and current_outputs.output_exists:
        output_state = dict(data.get("output_state", {}))
        output_state["output_exists"] = True
        if current_outputs.output_content_hash:
            output_state["output_content_hash"] = current_outputs.output_content_hash
        data["output_state"] = output_state

    # Attempt the write using freshness_manifest.save() (atomic os.replace pattern).
    try:
        new_manifest = _FM(data)
        _fm_save(new_manifest, state_root=effective_state_root)
    except Exception as exc:
        print(
            f"[GATE3-FAIL] Manifest write exception for {product}/{subdomain}: {exc}",
            file=_sys.stderr,
        )
        _restore_backup(manifest_path, backup_path)
        return False, f"manifest write FAILED ({exc}); backup restored"

    # Post-write verification: reload and confirm key fields are correct.
    try:
        verified = _fm_load(product, subdomain, state_root=effective_state_root)
        if verified is None:
            raise ValueError("re-load returned None after write")
        if verified.manifest_status != "FRESH":
            raise ValueError(
                f"manifest_status mismatch: expected FRESH, got {verified.manifest_status!r}"
            )
        if verified.product != product:
            raise ValueError(f"product mismatch in written manifest: {verified.product!r}")
        if verified.subdomain != subdomain:
            raise ValueError(f"subdomain mismatch in written manifest: {verified.subdomain!r}")
        if verified.run_id != run_id:
            raise ValueError(f"run_id mismatch in written manifest: {verified.run_id!r}")
        out_hash = verified.output_state.get("output_content_hash")
        if out_hash is not None and not out_hash.startswith("sha256:"):
            raise ValueError(f"output_content_hash is not sha256-prefixed: {out_hash!r}")
        gcf = verified.input_fingerprints.get("generator_code_hash")
        if gcf is not None and not gcf.startswith("sha256:"):
            raise ValueError(f"generator_code_hash is not sha256-prefixed: {gcf!r}")
    except Exception as exc:
        print(
            f"[GATE3-FAIL] Post-write verification failed for {product}/{subdomain}: {exc}",
            file=_sys.stderr,
        )
        _restore_backup(manifest_path, backup_path)
        return False, f"manifest write VERIFICATION FAILED ({exc}); backup restored"

    # Verification passed — remove backup.
    try:
        backup_path.unlink()
    except OSError:
        pass  # Non-fatal: backup cleanup failure is acceptable.

    print(
        f"[GATE3] Manifest write SUCCEEDED for {product}/{subdomain}: "
        f"run_id={run_id!r}, status=FRESH",
        file=_sys.stderr,
    )
    return True, f"manifest write SUCCEEDED (run_id={run_id!r})"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_harness(
    product: str,
    mode: str,
    scratch_root: Path,
    *,
    subdomains: list = None,
    synthetic_overrides: dict = None,
    triage_case: str = "",
    no_write: bool = True,
    restore_after: bool = False,
    run_id: str = "",
) -> dict:
    """Execute the harness for a single product and return a result dict.

    Args:
        product: Product slug "family/platform".
        mode: One of the valid harness modes.
        scratch_root: Directory for shadow output files (never content/).
        subdomains: Subdomains to evaluate. Defaults to all supported surfaces.
        synthetic_overrides: In-memory fingerprint overrides (not written to disk).
        triage_case: TC case ID to exercise (used in output metadata).
        no_write: If True, produce no files (default True).
        restore_after: If True, verify any temp modifications were restored.
        run_id: Run identifier. Auto-generated if empty.

    Returns:
        Dict with keys: product, mode, run_status, records, triage_case, run_id.

    Raises:
        ValueError: For invalid mode or missing required configuration.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"Invalid mode {mode!r}. Must be one of: {sorted(_VALID_MODES)}")

    if not _REGISTRY_PATH.is_file():
        raise ValueError(f"Registry not found: {_REGISTRY_PATH}")

    synthetic_overrides = synthetic_overrides or {}

    import datetime
    if not run_id:
        run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")

    registry = load_registry(_REGISTRY_PATH)
    tc_conditions = load_tc_closure_conditions(repo_root=_REPO_ROOT)

    # Determine which subdomains to evaluate
    if subdomains is None:
        subdomains = [
            name for name in registry.surface_names()
            if registry.get_surface(name).status in ("supported", "validate_only")
        ]

    surface_records = []
    expected_surfaces = [f"{product}/{sub}" for sub in subdomains]

    for subdomain in subdomains:
        try:
            surface = registry.get_surface(subdomain)
        except Exception as exc:
            surface_records.append(SurfaceRecord(
                product=product,
                subdomain=subdomain,
                decision=BLOCKED,
                outcome=BLOCKED,
                manifest_proof_path=None,
                explanation=f"Registry error: {exc}",
            ))
            continue

        # Collect fingerprints (with in-memory overrides for synthetic mode)
        if mode == "synthetic-input-change":
            fingerprints = _collect_fingerprints_with_overrides(
                product, subdomain, registry, synthetic_overrides
            )
        elif mode in ("dry-run", "validate-only", "force-reconcile"):
            fingerprints = _collect_fingerprints_with_overrides(
                product, subdomain, registry, {}
            )
        else:
            fingerprints = {}

        # TC-HEAL-003: Extract and remove the internal _collection_errors key so
        # it does not leak into fingerprint comparison, but preserve it for the record.
        fp_collection_errors = fingerprints.pop("_collection_errors", [])

        # Load stored manifest (skip for force-reconcile)
        if mode == "force-reconcile":
            stored = None
        else:
            stored = load_manifest(product, subdomain)

        # Inspect output state
        current_outputs = _inspect_output_state(product, subdomain, registry)

        # Compute decision
        d = decide(product, subdomain, fingerprints, current_outputs, stored)

        # TC-CHALLENGE-003: When decide() returns FRESH, run validate_for_fresh() to
        # catch cases where a required fingerprint is None (excluded from changed-set
        # by design at decision_engine line 134, so decide() cannot detect it).
        # This gate is required before any manifest write path is enabled.
        if d.decision == "FRESH":
            output_hash = current_outputs.output_content_hash if current_outputs else None
            generator_path = getattr(surface, "backing_generator", None)
            violations = validate_for_fresh(
                fingerprints,
                output_hash,
                generator_path=generator_path,
                repo_root=_REPO_ROOT,
                fingerprints_required=getattr(surface, "fingerprints_required", None),
            )
            if violations:
                import sys as _sys
                print(
                    f"[TC-CHALLENGE-003] FRESH blocked for {product}/{subdomain}: {violations}",
                    file=_sys.stderr,
                )
                # Rewrite decision as BLOCKED with violation details
                from decision_engine import Decision as _Decision
                d = _Decision(
                    product=product,
                    subdomain=subdomain,
                    decision=BLOCKED,
                    input_decision=BLOCKED,
                    output_decision=d.output_decision,
                    explanation="FRESH blocked by validate_for_fresh: " + "; ".join(violations),
                    changed_input_fingerprints=[],
                )

        # Gate 3a: gated manifest write (refreshes manifest timestamp on confirmed FRESH decision).
        # Only executes when refresh_manifest_write_enabled=True, refresh_reconciliation_enforced=True,
        # refresh_content_write_enabled=False, decision==FRESH, and no_write=False.
        manifest_write_note = ""
        if d.decision == "FRESH":
            _gate3_flags = load_feature_flags()
            # HARD_BLOCK: content writes are never permitted — halt entire run if detected.
            if _gate3_flags.get("refresh_content_write_enabled", False):
                raise RuntimeError(
                    "HARD_BLOCK: refresh_content_write_enabled=True detected in Gate 3 path. "
                    "This flag must remain false. Halting run."
                )
            if not no_write and _gate3_flags.get("refresh_manifest_write_enabled", False):
                _written, manifest_write_note = _write_manifest_gated(
                    product=product,
                    subdomain=subdomain,
                    fingerprints=fingerprints,
                    current_outputs=current_outputs,
                    stored=stored,
                    run_id=run_id,
                    flags=_gate3_flags,
                    no_write=no_write,
                )
                if not _written and "FAILED" in manifest_write_note:
                    # Write attempted but failed — mark surface BLOCKED.
                    from decision_engine import Decision as _Decision2
                    d = _Decision2(
                        product=product,
                        subdomain=subdomain,
                        decision=BLOCKED,
                        input_decision=d.input_decision,
                        output_decision=d.output_decision,
                        explanation=f"Manifest write failed: {manifest_write_note}",
                        changed_input_fingerprints=[],
                    )

        # Determine outcome for this mode
        # In dry-run: no action taken, outcome = SKIP (decision captured only)
        # In validate-only / synthetic: outcome mirrors decision (no writes)
        outcome = "SKIP"
        if d.decision in ("RECONCILE_MISSING", "RECONCILE_DRIFTED"):
            outcome = "SKIP"  # shadow only — no actual reconciliation
        elif d.decision == BLOCKED:
            outcome = BLOCKED
        elif d.decision == "FRESH":
            outcome = "SKIP"
        else:
            outcome = "SKIP"  # shadow mode: observe, don't act

        manifest_proof_path = None
        if d.decision == "FRESH" and stored is not None:
            # In a real run this would point to the manifest file
            manifest_proof_path = f"runs/state/{product}/{subdomain}/freshness-manifest.json"

        # Build explanation: append collection errors and manifest write notes.
        explanation = d.explanation
        if fp_collection_errors:
            explanation = (explanation + " | collection_errors: " + "; ".join(fp_collection_errors)).lstrip(" | ")
        if manifest_write_note:
            explanation = (explanation + " | " + manifest_write_note).lstrip(" | ")

        record = SurfaceRecord(
            product=product,
            subdomain=subdomain,
            decision=d.decision,
            outcome=outcome,
            manifest_proof_path=manifest_proof_path,
            explanation=explanation,
            changed_input_fingerprints=d.changed_input_fingerprints,
        )
        surface_records.append(record)

    # Build ledger
    ledger = build_ledger(run_id, surface_records, expected_surfaces, tc_conditions)

    # Override run_status for dry-run mode
    if mode == "dry-run" and ledger.run_status == PASS:
        ledger.run_status = DRY_RUN_PASS

    # Write shadow output (unless no_write)
    if not no_write and scratch_root:
        ledger.save(scratch_root, product)

    return {
        "product": product,
        "mode": mode,
        "run_status": ledger.run_status,
        "surfaces_silently_skipped": ledger.surfaces_silently_skipped,
        "partial_pass_surfaces": ledger.partial_pass_surfaces,
        "records": [r.to_dict() for r in ledger.records],
        "triage_case": triage_case,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="refresh_harness",
        description="Forced validation harness for the refresh decision engine (shadow mode).",
    )
    parser.add_argument("--product", required=True, help="Product slug 'family/platform'")
    parser.add_argument(
        "--mode",
        required=True,
        choices=sorted(_VALID_MODES),
        help="Harness execution mode",
    )
    parser.add_argument(
        "--scratch-root",
        default="",
        help="Directory for shadow output files (never content/)",
    )
    parser.add_argument(
        "--subdomain",
        dest="subdomains",
        action="append",
        default=None,
        help="Restrict to specific subdomain(s). Repeat for multiple.",
    )
    parser.add_argument(
        "--fingerprint",
        dest="fingerprints",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Synthetic fingerprint override (in-memory only, not written to disk). "
             "Format: upstream_repo_sha=SYNTHETIC_VALUE",
    )
    parser.add_argument(
        "--triage-case",
        default="",
        help="TC case ID being exercised (used in output metadata)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        default=True,
        help="Block all file writes (default: True)",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        default=False,
        help="Allow writing shadow output files to --scratch-root",
    )
    parser.add_argument(
        "--restore-after",
        action="store_true",
        default=False,
        help="Verify restore of any temporarily modified files (reserved for future use)",
    )
    parser.add_argument("--run-id", default="", help="Run identifier (auto-generated if empty)")

    args = parser.parse_args(argv)

    # Parse synthetic fingerprint overrides
    synthetic_overrides = {}
    for fp_spec in args.fingerprints:
        if "=" not in fp_spec:
            print(f"ERROR: --fingerprint must be NAME=VALUE, got: {fp_spec!r}", file=sys.stderr)
            return 2
        name, value = fp_spec.split("=", 1)
        synthetic_overrides[name.strip()] = value.strip()

    scratch_root = Path(args.scratch_root) if args.scratch_root else Path(".")
    no_write = not args.allow_write

    try:
        result = run_harness(
            product=args.product,
            mode=args.mode,
            scratch_root=scratch_root,
            subdomains=args.subdomains,
            synthetic_overrides=synthetic_overrides,
            triage_case=args.triage_case,
            no_write=no_write,
            restore_after=args.restore_after,
            run_id=args.run_id,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Output result summary
    print(json.dumps(result, indent=2, ensure_ascii=False))

    run_status = result.get("run_status", FAIL)
    if run_status in (PASS, DRY_RUN_PASS):
        return 0
    elif run_status == BLOCKED:
        return 1
    else:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
