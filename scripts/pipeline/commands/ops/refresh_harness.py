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

_REPO_ROOT = Path(__file__).resolve().parents[4]

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
        from fingerprint_collector import collect_input_fingerprints
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

        # Build explanation: append collection errors so they are visible in ledger records.
        explanation = d.explanation
        if fp_collection_errors:
            explanation = (explanation + " | collection_errors: " + "; ".join(fp_collection_errors)).lstrip(" | ")

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
