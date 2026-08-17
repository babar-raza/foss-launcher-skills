"""Pilot rerun for MT033-WAECOLLISION-001: exercises the real production
batch_reference.run() entrypoint (the same function the CLI's main() calls)
against an isolated, disposable pilot workspace -- a first-time reference-page
generation for a synthetic product "pilotfam/net", with a genuine writer crash
simulated on the real (non-staging) write path, then a retry after a REAL
1.5-second wall-clock sleep, crossing a real clock-second boundary.

Only one thing is simulated: the crash itself, via safe_content_write --
exactly the same injection point this codebase's own regression test
(test_reference_write_ahead_evidence_survives_writer_crash) uses to validate
this property. Everything else -- config resolution, candidate selection,
page building, run-scope validation, receipt emission, decision-row
comparison -- is real, unmodified production code.

One-off diagnostic script (scripts/maintenance/ convention) -- not wired into
any skill/CI/hook. Writes only under a caller-supplied pilot_root directory
(never the real repo tree).

Usage: .venv/Scripts/python scripts/maintenance/pilot_wae_collision_repro.py <label> <pilot_root>
  <label>      "BEFORE" or "AFTER" -- just used in the printed banner
  <pilot_root> fresh directory to build the pilot fixture in
"""
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "content"))

import batch_reference as br  # noqa: E402


def build_pilot(pilot_root: Path) -> tuple[Path, str]:
    if pilot_root.exists():
        shutil.rmtree(pilot_root)
    pilot_root.mkdir(parents=True)

    merged = pilot_root / "knowledge" / "pilotfam" / "net" / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text(
        json.dumps([{
            "name": "Widget",
            "kind": "class_declaration",
            "methods": [],
            "properties": [],
        }]),
        encoding="utf-8",
    )
    import yaml
    (merged / "model.yaml").write_text(
        yaml.safe_dump({"stale_since": None, "version": "1.0.0", "repo_sha": "pilot-fixture-sha"}),
        encoding="utf-8",
    )

    run_id = "RUN-PILOT-WAE-001"
    run_root = pilot_root / "reports" / "refresh_runs" / "pilotfam" / "net" / run_id
    run_root.mkdir(parents=True)
    scoped = "content/reference.aspose.org/en/pilotfam/net/Widget.md"
    scope_path = run_root / "scope.json"
    scope_path.write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": run_id,
            "family": "pilotfam",
            "platform": "net",
            "paths": [scoped],
            "initial_hashes": {},
        }),
        encoding="utf-8",
    )
    logical = json.dumps(
        {"paths": [scoped], "input_digest": None},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    (run_root / "manifest.json").write_text(
        json.dumps({
            "run_id": run_id,
            "family": "pilotfam",
            "platform": "net",
            "created_at": "2026-08-01T09:00:00Z",
            "scope": {
                "paths": [scoped],
                "input_digest": None,
                "digest": "sha256:" + hashlib.sha256(logical).hexdigest(),
            },
            "output_digests": {
                "scope": "sha256:" + hashlib.sha256(scope_path.read_bytes()).hexdigest()
            },
        }),
        encoding="utf-8",
    )
    return run_root, run_id


def main():
    label = sys.argv[1]
    pilot_root = Path(sys.argv[2])
    run_root, run_id = build_pilot(pilot_root)

    br.configure(repo_root=pilot_root)
    page_path = pilot_root / "content/reference.aspose.org/en/pilotfam/net/Widget.md"

    print(f"===== PILOT [{label}] : first-time page generation, crash mid-write, retry after real clock delay =====")
    print(f"pilot_root={pilot_root}")
    print(f"page (before any run) exists: {page_path.exists()}")

    original_write = br.safe_content_write

    def crash_on_real_path(path, content, **kwargs):
        if str(path).startswith(str(run_root / "staging")):
            return original_write(path, content, **kwargs)
        raise RuntimeError("SIMULATED WRITER CRASH (pilot)")

    br.safe_content_write = crash_on_real_path
    print("\n--- RUN 1 (will crash) ---")
    t0 = time.time()
    result1 = br.run(
        "pilotfam", "net",
        confirm_rebuild=True,
        run_id=run_id,
        run_root=run_root,
    )
    print(f"result1 = {json.dumps(result1, default=str)}")
    print(f"page exists after crash: {page_path.exists()}")

    br.safe_content_write = original_write

    delay = 1.5
    print(f"\n--- sleeping {delay}s (real wall clock, crossing a real clock-second boundary) ---")
    time.sleep(delay)
    print(f"elapsed since RUN 1 started: {time.time() - t0:.2f}s")

    print("\n--- RUN 2 (retry, same run_id/run_root, no crash) ---")
    try:
        result2 = br.run(
            "pilotfam", "net",
            confirm_rebuild=True,
            run_id=run_id,
            run_root=run_root,
        )
        print(f"result2 = {json.dumps(result2, default=str)}")
        collision = False
    except FileExistsError as exc:
        print(f"COLLISION RAISED: {exc}")
        result2 = None
        collision = True

    print("\n--- final page content ---")
    if page_path.exists():
        print(page_path.read_text(encoding="utf-8"))
    else:
        print("(page does not exist)")

    decisions_path = run_root / "page_decisions.jsonl"
    print("--- page_decisions.jsonl ---")
    if decisions_path.exists():
        print(decisions_path.read_text(encoding="utf-8"))
    else:
        print("(no decisions file)")

    print(f"\n===== SUMMARY [{label}] =====")
    print(f"run1_errors={result1.get('errors')} run1_updated={result1.get('updated')} run1_generated={result1.get('generated')}")
    if collision:
        print("run2: FileExistsError (Page decision collision) -- retry BLOCKED")
    else:
        print(f"run2_errors={result2.get('errors')} run2_updated={result2.get('updated')} run2_generated={result2.get('generated')}")
    print(f"final_page_exists={page_path.exists()}")

    br.configure()


if __name__ == "__main__":
    main()
