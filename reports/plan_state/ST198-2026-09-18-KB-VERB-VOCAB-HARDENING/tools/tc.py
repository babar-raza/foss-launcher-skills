"""tc.py - taskcard driver for PLAN-ST198 (thin wrapper over the schema-5f TaskcardStore).
authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
artifact_role: execution_tooling_not_a_plan
execution_authority: false
Run from the repo root:  PYTHONPATH=scripts/pipeline .venv/Scripts/python <this file> <command> ...
The store (reports/plan_state/<mission>/taskcards.jsonl) stays the only status authority; this script only
refuses illegal writes and appends the per-card execution log.
"""
import argparse, datetime, hashlib, json, os, re, shutil, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.getcwd(), "scripts", "pipeline"))
from lib.taskcard_store import TaskcardStore, TaskcardAlreadyExistsError

MISSION = "ST198-2026-09-18-KB-VERB-VOCAB-HARDENING"
PLAN_ID = "PLAN-ST198-KB-VERB-VOCAB-HARDENING"
CHILD_OK = {"TODO": {"READY"}, "READY": {"IN_PROGRESS"}, "IN_PROGRESS": {"IMPLEMENTED"},
            "IMPLEMENTED": {"FOCUSED_VERIFIED"}, "FOCUSED_VERIFIED": {"CLOSED"},
            "REWORK_REQUIRED": {"IN_PROGRESS"}, "BLOCKED_LOCAL": {"READY"},
            "BLOCKED_EXTERNAL": {"READY"}, "PAUSED": {"READY"}}
PARENT_OK = {"TODO": {"READY"}, "READY": {"IN_PROGRESS"}, "IN_PROGRESS": {"INTEGRATION_VERIFIED"},
             "INTEGRATION_VERIFIED": {"END_TO_END_VERIFIED"},
             "END_TO_END_VERIFIED": {"INDEPENDENTLY_REVIEWED", "CLOSED"},
             "INDEPENDENTLY_REVIEWED": {"CLOSED"}, "REWORK_REQUIRED": {"IN_PROGRESS"},
             "BLOCKED_LOCAL": {"READY"}, "BLOCKED_EXTERNAL": {"READY"}, "PAUSED": {"READY"}}
INTERRUPT = {"REWORK_REQUIRED", "BLOCKED_LOCAL", "BLOCKED_EXTERNAL", "PAUSED", "OUT_OF_SCOPE", "SUPERSEDED"}
TERMINAL = {"CLOSED", "OUT_OF_SCOPE", "SUPERSEDED"}
PRE_EVIDENCE = {"TODO", "READY", "IN_PROGRESS", "IMPLEMENTED"}
CHILD_DIMS = ["requirement_correctness", "implementation_correctness", "scope_discipline", "validation_strength",
              "evidence_completeness", "regression_safety", "maintainability", "production_readiness"]
PARENT_DIMS = ["root_cause_coverage", "child_completeness", "integration_completeness", "dependency_correctness",
               "preserved_behavior", "evidence_completeness", "rerun_consistency", "production_readiness"]
SECRET_RX = [re.compile(p) for p in (r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
             r"x-access-token:(?!\*\*\*)[^@\s]+@", r"GH_TOKEN\s*=\s*\S+", r"Authorization:\s*(?:token|Bearer)\s+\S+")]
ABSPATH_RX = re.compile(r"(?:[A-Za-z]:[\\/](?:Users|onedrive|Windows)|/[cd]/(?:Users|onedrive)|C:\\WINDOWS)", re.I)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def die(msg):
    print("REFUSED:", msg, file=sys.stderr)
    sys.exit(2)


def get_store(a):
    return TaskcardStore(a.mission, plan_state_dir=a.store_dir) if a.store_dir else TaskcardStore(a.mission)


def evidence_dir(st):
    return os.path.join(os.path.dirname(str(st.path)), "evidence")


def parse_plan(plan_path):
    text = open(plan_path, encoding="utf-8").read()
    heads = list(re.finditer(r"^(#{2,4}) (.*)$", text, re.M))
    tcre = re.compile(r"^(TC-ST198-\d\d(?:-\d\d)?) \u2014 (.+)$")
    msre = re.compile(r"^\|\s*(MS-ST198-\d\d-\d\d-\d\d)\s*\|", re.M)
    rows = []
    for i, h in enumerate(heads):
        m = tcre.match(h.group(2))
        if not m:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end]
        tid, title = m.group(1), m.group(2).strip()
        kind = "PARENT" if h.group(1) == "###" else "CHILD"

        def lst(key, body=body):
            mm = re.search(r"^" + key + r":\s*\[(.*?)\]", body, re.M)
            return [x.strip() for x in mm.group(1).split(",")] if mm and mm.group(1).strip() else []

        rows.append(dict(task_id=tid, mission_id=None, title=title, task_kind=kind,
                         parent_task_id=(tid.rsplit("-", 1)[0] if kind == "CHILD" else None),
                         requirement_ids=lst("req"), dependencies=lst("deps"), status="TODO",
                         recorded_by="seed-from-plan", evidence_refs=[],
                         micro_steps_total=(len(msre.findall(body)) if kind == "CHILD" else 0), plan_ref=PLAN_ID))
    return rows


def cmd_seed(a):
    rows = parse_plan(a.plan)
    ids = [r["task_id"] for r in rows]
    if len(ids) != len(set(ids)):
        die("duplicate task ids in plan")
    print("parents:", sum(r["task_kind"] == "PARENT" for r in rows), "children:", sum(r["task_kind"] == "CHILD" for r in rows),
          "micro_steps:", sum(r["micro_steps_total"] for r in rows))
    if a.dry_run:
        for r in rows:
            print(r["task_id"], r["task_kind"], "req=", r["requirement_ids"], "deps=", r["dependencies"], "ms=", r["micro_steps_total"])
        return 0
    st = get_store(a)
    created = skipped = 0
    for r in rows:
        r["mission_id"] = a.mission
        r["recorded_at"] = now()
        try:
            st.append(r, expect_absent=True)
            created += 1
        except TaskcardAlreadyExistsError:
            skipped += 1
    print("created:", created, "skipped(existing):", skipped)
    return 0


def log_line(st, task, text):
    d = os.path.join(evidence_dir(st), "taskcards")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, task + ".md")
    if not os.path.exists(p):
        open(p, "w", encoding="utf-8").write(
            f"authoritative_plan: {PLAN_ID}\nrequirement: see store row\ntaskcard: {task}\nmicro_step: (per line)\n\n")
    open(p, "a", encoding="utf-8").write(f"- {now()} {text}\n")


def cmd_advance(a):
    st = get_store(a)
    latest = st.read_latest()
    cur = latest.get(a.task)
    if cur is None:
        die(f"unknown task {a.task}")
    kind, old, new = cur.get("task_kind", "CHILD"), cur["status"], a.status
    ok = PARENT_OK if kind == "PARENT" else CHILD_OK
    done = sorted(set(cur.get("micro_steps_done", [])) | set(a.done or []))
    skipped = dict(cur.get("micro_steps_skip_reasons", {}))
    for s in a.skipped or []:
        k, _, why = s.partition("=")
        if not why.strip():
            die(f"skipped micro-step {k} needs a reason (ID=reason)")
        skipped[k] = why.strip()
    ev = list(cur.get("evidence_refs", []))
    for e in a.evidence or []:
        if e not in ev:
            ev.append(e)
    extra = {"micro_steps_done": done, "micro_steps_skipped": sorted(skipped), "micro_steps_skip_reasons": skipped}
    if old in TERMINAL:
        die(f"{a.task} is terminal ({old})")
    if new == old:
        if not (a.done or a.skipped):
            die("same-status update needs --done or --skipped")
    elif new in INTERRUPT:
        if new == "PAUSED" and not a.pause_reason:
            die("PAUSED needs --pause-reason")
        if new in ("OUT_OF_SCOPE", "SUPERSEDED", "BLOCKED_EXTERNAL") and not a.note:
            die(f"{new} needs --note (reason / external action / resume condition)")
        if new == "REWORK_REQUIRED" and not a.note:
            die("REWORK_REQUIRED needs --note naming the weak dimension or defect")
    elif new not in ok.get(old, set()):
        die(f"illegal transition {old} -> {new} for a {kind}")
    if new == "READY" and old == "TODO":
        bad = [d for d in cur.get("dependencies", []) if latest.get(d, {}).get("status") != "CLOSED"]
        if bad:
            die(f"dependencies not CLOSED: {bad}")
    if new == "IN_PROGRESS" and kind == "CHILD":
        par = latest.get(cur.get("parent_task_id"))
        if par is None:
            die("child has no parent row")
        if par["status"] in ("TODO", "READY"):
            bad = [d for d in par.get("dependencies", []) if latest.get(d, {}).get("status") != "CLOSED"]
            if bad:
                die(f"parent dependencies not CLOSED: {bad}")
            if par["status"] == "TODO":
                st.update_taskcard_status(par["task_id"], expected_status="TODO", new_status="READY", recorded_by=a.by)
            st.update_taskcard_status(par["task_id"], expected_status="READY", new_status="IN_PROGRESS", recorded_by=a.by)
            log_line(st, par["task_id"], "auto LP-1: READY -> IN_PROGRESS (first child started)")
        elif par["status"] != "IN_PROGRESS":
            die(f"parent is {par['status']}; cannot start a child")
    if new not in PRE_EVIDENCE and new not in INTERRUPT and not ev:
        die(f"{new} needs --evidence")
    if new in ("INTEGRATION_VERIFIED", "END_TO_END_VERIFIED", "INDEPENDENTLY_REVIEWED", "CLOSED") and kind == "PARENT":
        kids = [t for t, r in latest.items() if r.get("parent_task_id") == a.task]
        if new in ("INTEGRATION_VERIFIED", "CLOSED"):
            openk = [k for k in kids if latest[k]["status"] != "CLOSED"]
            if not kids or openk:
                die(f"children not all CLOSED: {openk or 'none registered'}")
    if new == "CLOSED":
        dims = PARENT_DIMS if kind == "PARENT" else CHILD_DIMS
        sc = {d: a.score_all for d in dims} if a.score_all else {}
        for s in a.score or []:
            k, _, v = s.partition("=")
            sc[k] = int(v)
        missing = [d for d in dims if d not in sc]
        if missing or min(sc.get(d, 0) for d in dims) < 4:
            die(f"CLOSED needs every {kind} dimension scored >= 4; missing/low: {missing or {d: sc[d] for d in dims if sc[d] < 4}}")
        extra["quality_scores"] = {d: sc[d] for d in dims}
        if kind == "CHILD" and len(done) + len(skipped) != cur.get("micro_steps_total", -1):
            die(f"micro-steps {len(done)} done + {len(skipped)} skipped != total {cur.get('micro_steps_total')}")
    if new == "IMPLEMENTED" and kind == "CHILD" and len(done) + len(skipped) != cur.get("micro_steps_total", -1):
        die(f"IMPLEMENTED needs every micro-step done or skipped-with-reason ({len(done)}+{len(skipped)}/{cur.get('micro_steps_total')})")
    if a.pause_reason:
        extra["pause_reason"] = a.pause_reason
    if a.note:
        extra["note"] = a.note
    st.update_taskcard_status(a.task, expected_status=old, new_status=new, recorded_by=a.by, evidence_refs=ev, **extra)
    log_line(st, a.task, f"{old} -> {new} by {a.by}; done={len(done)}/{cur.get('micro_steps_total', 0)}; evidence+={len(a.evidence or [])}"
             + (f"; note={a.note}" if a.note else ""))
    print(f"{a.task}: {old} -> {new}")
    return 0


def audit_rows(st):
    seq = {}
    for r in st.read_history():
        seq.setdefault(r["task_id"], []).append(r)
    latest = {t: rows[-1] for t, rows in seq.items()}
    bad = []
    for tid, rows in seq.items():
        kind = rows[0].get("task_kind", "CHILD")
        ok = PARENT_OK if kind == "PARENT" else CHILD_OK
        if rows[0]["status"] not in ("TODO", "READY"):
            bad.append(f"{tid}: first row status {rows[0]['status']} (must seed TODO/READY)")
        for x, y in zip(rows, rows[1:]):
            sa, sb = x["status"], y["status"]
            if sa in TERMINAL:
                bad.append(f"{tid}: row after terminal {sa} -> {sb}")
            elif sa == sb:
                if len(y.get("micro_steps_done", [])) < len(x.get("micro_steps_done", [])):
                    bad.append(f"{tid}: micro_steps_done shrank at status {sa}")
            elif sb in INTERRUPT:
                pass
            elif sb not in ok.get(sa, set()):
                bad.append(f"{tid}: illegal transition {sa} -> {sb}")
            if sb not in PRE_EVIDENCE and sb not in INTERRUPT and not y.get("evidence_refs"):
                bad.append(f"{tid}: {sb} without evidence_refs")
        last = rows[-1]
        if last["status"] == "CLOSED":
            if kind == "CHILD":
                qs = last.get("quality_scores") or {}
                if set(qs) != set(CHILD_DIMS) or min(qs.values()) < 4:
                    bad.append(f"{tid}: CLOSED without all 8 quality_scores >= 4 ({qs})")
                n = len(last.get("micro_steps_done", [])) + len(last.get("micro_steps_skipped", []))
                if n != last.get("micro_steps_total", -1):
                    bad.append(f"{tid}: CLOSED with micro-steps {n}/{last.get('micro_steps_total')}")
            else:
                kids = [t for t, r in latest.items() if r.get("parent_task_id") == tid]
                openk = [k for k in kids if latest[k]["status"] != "CLOSED"]
                if not kids or openk:
                    bad.append(f"{tid}: parent CLOSED but children not all CLOSED: {openk or 'none registered'}")
    return bad, latest


def cmd_audit(a):
    bad, latest = audit_rows(get_store(a))
    print(f"rows(latest)={len(latest)}")
    print("PASS (0 violations)" if not bad else "\n".join(bad))
    return 1 if bad else 0


def cmd_show(a):
    latest = get_store(a).read_latest()
    for t in sorted(latest):
        r = latest[t]
        if a.task and t != a.task:
            continue
        print(f"{t:16s} {r.get('task_kind','?'):6s} {r['status']:20s} ms={len(r.get('micro_steps_done', []))}/{r.get('micro_steps_total', 0)} deps={r.get('dependencies', [])}")
    return 0


def cmd_next(a):
    latest = get_store(a).read_latest()
    cands = []
    for t, r in sorted(latest.items()):
        if r.get("task_kind") != "CHILD" or r["status"] not in ("TODO", "READY", "IN_PROGRESS", "REWORK_REQUIRED"):
            continue
        deps = r.get("dependencies", [])
        pdeps = latest[r["parent_task_id"]].get("dependencies", [])
        if all(latest.get(d, {}).get("status") == "CLOSED" for d in deps + pdeps):
            cands.append(t)
    print(cands[0] if cands else "NONE (all children terminal or blocked)")
    return 0


def cmd_bundle(a):
    st = get_store(a)
    root = evidence_dir(st)
    if not os.path.isdir(root):
        die("no evidence directory")
    snap = os.path.join(root, "closeout")
    os.makedirs(snap, exist_ok=True)
    shutil.copyfile(str(st.path), os.path.join(snap, "taskcards.snapshot.jsonl"))
    problems, lines = [], []
    for base, _, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(base, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            if rel == "MANIFEST.sha256":
                continue
            data = open(p, "rb").read()
            lines.append(f"{hashlib.sha256(data).hexdigest()}  {rel}")
            if not data:
                problems.append(f"empty file: {rel}")
            try:
                txt = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for rx in SECRET_RX:
                if rx.search(txt):
                    problems.append(f"possible secret in {rel}: {rx.pattern}")
            if ABSPATH_RX.search(txt) and not rel.startswith("generated-artifacts/"):
                problems.append(f"absolute local path in {rel}")
    lines.sort(key=lambda s: s.split("  ", 1)[1])
    open(os.path.join(root, "MANIFEST.sha256"), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print(f"manifest: {len(lines)} files")
    print("bundle root:", os.path.abspath(root))
    print("PASS (0 problems)" if not problems else "\n".join(problems))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description="PLAN-ST198 taskcard driver")
    ap.add_argument("--mission", default=MISSION)
    ap.add_argument("--store-dir", default=None, help="tests only: alternate plan_state dir")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed"); s.add_argument("plan"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_seed)
    s = sub.add_parser("advance"); s.add_argument("task"); s.add_argument("status"); s.add_argument("--by", required=True)
    s.add_argument("--evidence", nargs="*"); s.add_argument("--done", nargs="*"); s.add_argument("--skipped", nargs="*")
    s.add_argument("--score", nargs="*"); s.add_argument("--score-all", type=int); s.add_argument("--note"); s.add_argument("--pause-reason")
    s.set_defaults(fn=cmd_advance)
    s = sub.add_parser("audit"); s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("show"); s.add_argument("task", nargs="?"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("next"); s.set_defaults(fn=cmd_next)
    s = sub.add_parser("bundle"); s.set_defaults(fn=cmd_bundle)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
