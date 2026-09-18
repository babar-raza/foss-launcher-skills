import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PY = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "commands" / "foss" / "readme_refresh_run.py"
MISSION_DIR = Path(__file__).resolve().parent

products = json.loads((REPO_ROOT / "data" / "products.json").read_text(encoding="utf-8"))

results = {}
for p in products:
    fam, plat = p["family"], p["platform"]
    key = f"{fam}/{plat}"
    t0 = time.time()
    try:
        proc = subprocess.run(
            [str(PY), str(SCRIPT), "audit-portfolio", "--family", fam, "--platform", plat, "--json"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=400,
            env={"PYTHONPATH": str(REPO_ROOT / "scripts" / "pipeline")},
        )
        elapsed = round(time.time() - t0, 1)
        stdout = proc.stdout.strip()
        parsed = json.loads(stdout) if stdout else None
        results[key] = {"returncode": proc.returncode, "elapsed_s": elapsed, "parsed": parsed}
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - t0, 1)
        results[key] = {"returncode": None, "elapsed_s": elapsed, "parsed": None, "error": "TIMEOUT_400s"}
    print(f"{key}: rc={results[key].get('returncode')} elapsed={results[key]['elapsed_s']}s", file=sys.stderr, flush=True)

out_path = MISSION_DIR / "post_fix_audit_results.json"
out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\nWrote {out_path}", file=sys.stderr)
