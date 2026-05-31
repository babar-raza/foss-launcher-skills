# scripts/maintenance/supervisor — Local Supervisor Control Plane for aspose.org pipeline
# NOTE: Originally planned as tools/supervisor/ but adjusted to scripts/maintenance/supervisor/
#       due to write-path governance (path_guard.py allowlist). scripts/maintenance/ is the
#       correct location for operator maintenance tools per AGENTS.md §4b.
# All scripts are deterministic Python. No LLM calls. Read-only in dry-run mode.
