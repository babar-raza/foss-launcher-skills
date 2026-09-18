"""One-off DAG validator for MT064's taskcards.jsonl (SEO-PLAN-NORMALIZE-G1
acceptance check): no dangling deps, no cycles, no self-deps. Scratch script
under reports/plan_state/ (gitignored, tier-1 writable), read-only."""
import json
import sys

path = sys.argv[1]
rows = {}
with open(path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        rows[obj["task_id"]] = obj  # last wins

errors = []
for tid, row in rows.items():
    for dep in row.get("dependencies") or []:
        if dep == tid:
            errors.append(f"self-dep: {tid}")
        if dep not in rows:
            errors.append(f"dangling dep: {tid} -> {dep} (not in store)")

# Cycle detection via DFS.
WHITE, GRAY, BLACK = 0, 1, 2
color = {tid: WHITE for tid in rows}


def visit(tid, stack):
    if color[tid] == BLACK:
        return
    if color[tid] == GRAY:
        errors.append(f"cycle: {' -> '.join(stack + [tid])}")
        return
    color[tid] = GRAY
    for dep in rows[tid].get("dependencies") or []:
        if dep in rows:
            visit(dep, stack + [tid])
    color[tid] = BLACK


for tid in rows:
    visit(tid, [])

print(f"checked {len(rows)} rows")
if errors:
    for e in errors:
        print("ERROR:", e)
    sys.exit(1)
print("OK: no dangling deps, no cycles, no self-deps")
