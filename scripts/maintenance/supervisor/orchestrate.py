"""
orchestrate.py — Master supervisor loop: discover -> validate -> compare -> generate -> sync.

Dry-run exits 0 for DRY_RUN_COMPLETE and NO_ACTIONS_READY (both valid).
Execute mode (MODE 5 approved): writes sprint prompt, backlog/HANDOFF.md, and dashboard.
Fatal errors exit 1.
"""
from __future__ import annotations
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit
from discover import discover
from validate import validate
from compare import compare
from generate import generate
from sync import sync


def _read_active_backlog_items(repo_root, max_items=5):
    """Read non-CLOSED P0/P1 items from backlog/BACKLOG.md Active section.

    Returns list of dicts: [{id, title, status, priority}], or [] if not readable.
    """
    import re as _re
    backlog_path = Path(repo_root) / "backlog" / "BACKLOG.md"
    if not backlog_path.exists():
        return []
    try:
        text = backlog_path.read_text(encoding="utf-8")
        active_match = _re.search(r"## Active.*?(?=\n## |\Z)", text, _re.DOTALL)
        if not active_match:
            return []
        items = []
        for line in active_match.group(0).splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 7:
                continue
            item_id = parts[1].strip()
            if not item_id or not _re.match(r"[A-Z][A-Z0-9-]+-\d+", item_id):
                continue
            title = parts[4].strip()[:80]
            status = parts[5].strip()
            priority = parts[6].strip()
            if status.upper() in ("CLOSED", "STATUS"):
                continue
            items.append({"id": item_id, "title": title, "status": status, "priority": priority})
            if len(items) >= max_items:
                break
        return items
    except Exception:
        return []


def _read_last_action(repo_root):
    """Read last_action from .supervisor/state/current.json, or None."""
    state_path = Path(repo_root) / ".supervisor" / "state" / "current.json"
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state.get("last_action")
    except Exception:
        return None


def _build_handoff(trace, gen, comp, run_id, now, repo_root):
    """Build HANDOFF.md content for execute mode (MODE 5) with actionable context."""
    disc_stage = trace["stages"].get("discover", {})
    comp_stage = trace["stages"].get("compare", {})
    selected_type = gen.get("selected_action_type", "NO_ACTIONS_READY")
    selected_action = gen.get("selected_action", {})
    status = trace.get("status", "UNKNOWN")

    # Active backlog items (read-only)
    active_items = _read_active_backlog_items(repo_root)
    if active_items:
        backlog_lines = "\n".join(
            f"  - [{item['priority']}] {item['id']} — {item['title']} ({item['status']})"
            for item in active_items
        )
    else:
        backlog_lines = "  (No open P0/P1 items — all Active items are CLOSED or backlog absent)"

    # Full skill chain for selected action
    suggested_skills = selected_action.get("suggested_skills", [])
    if suggested_skills:
        family = selected_action.get("family", "{family}")
        platform = selected_action.get("platform", "{platform}")
        skill_lines = "\n".join(
            "  " + s.replace("{family}", family).replace("{platform}", platform)
            for s in suggested_skills
        )
    else:
        skill_lines = f"  (No skill chain — action type: {selected_type})"

    # Last session action from state
    last_action = _read_last_action(repo_root)
    last_session_line = (
        f"  {last_action}" if last_action and last_action != "none"
        else "  (no prior session recorded)"
    )

    # Next session recommendations based on action type
    if selected_type == "HEAL_PAGES":
        page_count = selected_action.get("count", 0)
        next_bullets = (
            f"  1. Run /heal-page on the {page_count} Grade D/F pages in the sprint prompt\n"
            f"  2. Re-run content_eval after healing to confirm grade improvement\n"
            f"  3. Commit healed pages with /commit when eval passes"
        )
    elif selected_type == "ENRICH_PAGES":
        page_count = selected_action.get("count", 0)
        next_bullets = (
            f"  1. Run /page-enhance on the {page_count} Grade C pages in the sprint prompt\n"
            f"  2. Verify evidence blocks are attached after enrichment\n"
            f"  3. Commit enriched pages with /commit when eval passes"
        )
    elif selected_type == "REFRESH_PRODUCT":
        family = selected_action.get("family", "?")
        platform = selected_action.get("platform", "?")
        next_bullets = (
            f"  1. Run /knowledge-diff {family} {platform} to confirm upstream changes\n"
            f"  2. Run full skill chain from sprint prompt (/knowledge-update through /family-sync)\n"
            f"  3. Commit all changes with /commit"
        )
    elif selected_type == "INVESTIGATE_MISSING_STATE":
        next_bullets = (
            f"  1. Run /repo-scout to bootstrap knowledge for missing products\n"
            f"  2. Re-run orchestrate to re-assess after scout completes\n"
            f"  3. Escalate to operator if repo access is blocked"
        )
    else:
        next_bullets = (
            f"  1. Review BACKLOG.md Active section for open P0/P1 items\n"
            f"  2. Run orchestrate --dry-run to confirm repo state\n"
            f"  3. Proceed with highest-priority open backlog item"
        )

    return (
        f"# Session Handoff — Supervisor RC\n"
        f"Run: {run_id}\n"
        f"Generated: {now.isoformat()}\n"
        f"Mode: EXECUTE\n"
        f"\n"
        f"## Pipeline Status\n"
        f"- Status: {status}\n"
        f"- Stale products: {disc_stage.get('stale', 0)}\n"
        f"- Fresh products: {disc_stage.get('fresh', 0)}\n"
        f"- Missing products: {disc_stage.get('missing', 0)}\n"
        f"- Actions identified: {comp_stage.get('action_count', 0)}\n"
        f"\n"
        f"## Active Backlog Items (P0/P1, non-CLOSED)\n"
        f"{backlog_lines}\n"
        f"\n"
        f"## Selected Action\n"
        f"Type: {selected_type}\n"
        f"Reason: {selected_action.get('reason', '—')}\n"
        f"\n"
        f"### Skill Chain\n"
        f"{skill_lines}\n"
        f"\n"
        f"## Last Session\n"
        f"{last_session_line}\n"
        f"\n"
        f"## Next Session Should\n"
        f"{next_bullets}\n"
        f"\n"
        f"## Evidence\n"
        f"- Run trace: reports/supervisor/run-{run_id}.json\n"
        f"- Sprint prompt: reports/supervisor/next-sprint-{run_id}.md\n"
        f"- Dashboard: reports/supervisor/dashboard-{run_id}.md\n"
        f"\n"
        f"---\n"
        f"Generated by Local Supervisor Control Plane (deterministic, no LLM).\n"
    )


def _build_dashboard(trace, disc, val, comp, gen, syn, run_id, now, dry_run):
    """Build human-readable dashboard report."""
    disc_s = trace["stages"].get("discover", {})
    val_s = trace["stages"].get("validate", {})
    comp_s = trace["stages"].get("compare", {})
    gen_s = trace["stages"].get("generate", {})
    handoff_s = trace["stages"].get("handoff_write", {})
    grade_str = json.dumps(val_s.get("grade_summary", {}), separators=(", ", ": "))
    mode_label = "DRY-RUN" if dry_run else "EXECUTE"
    actions_block = ""
    if comp["actions"]:
        for a in comp["actions"]:
            actions_block += f"  - [{a.get('priority')}] {a['type']}"
            if a.get("family"):
                actions_block += f" {a['family']}/{a.get('platform', '')}"
            actions_block += f" — {a.get('reason', '')}\n"
    else:
        actions_block = "  None (repo is fresh)\n"

    handoff_line = ""
    if handoff_s:
        handoff_line = f"\n## HANDOFF.md\nWritten to: {handoff_s.get('path', 'backlog/HANDOFF.md')}\n"
    else:
        handoff_line = "\n## HANDOFF.md\nNot written (dry-run mode)\n"

    return (
        f"# Supervisor RC Dashboard\n"
        f"Run: {run_id}\n"
        f"Generated: {now.isoformat()}\n"
        f"Mode: {mode_label}\n"
        f"Status: {trace['status']}\n"
        f"\n"
        f"## Pipeline Stages\n"
        f"| Stage | Status | Key Metrics |\n"
        f"|-------|--------|-------------|\n"
        f"| discover | {disc_s.get('status', '?')} | "
        f"stale={disc_s.get('stale', 0)} fresh={disc_s.get('fresh', 0)} missing={disc_s.get('missing', 0)} |\n"
        f"| validate | {val_s.get('status', '?')} | "
        f"eval_files={val_s.get('eval_files', 0)} heal_needed={val_s.get('pages_needing_heal', 0)} |\n"
        f"| compare | {comp_s.get('status', '?')} | "
        f"actions={comp_s.get('action_count', 0)} backlog={comp_s.get('backlog_status', '?')} |\n"
        f"| generate | {gen_s.get('status', '?')} | "
        f"selected={gen_s.get('selected_action', '?')} |\n"
        f"| sync | {syn.get('status', '?')} | "
        f"sprint_count={syn.get('state', {}).get('sprint_count', '?')} |\n"
        f"\n"
        f"## Grade Summary\n"
        f"{grade_str or '(no eval reports)'}\n"
        f"\n"
        f"## Actions\n"
        f"{actions_block}"
        f"{handoff_line}"
        f"\n"
        f"## Warnings ({len(trace['warnings'])})\n"
        + ("\n".join(f"  - {w}" for w in trace["warnings"][:10]) or "  None")
        + "\n\n"
        f"## Evidence Paths\n"
        f"- Run trace: reports/supervisor/run-{run_id}.json\n"
        f"- Sprint prompt: reports/supervisor/next-sprint-{run_id}.md\n"
        f"- Dashboard: reports/supervisor/dashboard-{run_id}.md\n"
    )


def orchestrate(dry_run=True, repo_root=None):
    root = Path(repo_root or REPO_ROOT)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%d-%H%M%S")
    trace = {
        "run_id": run_id,
        "started_at": now.isoformat(),
        "dry_run": dry_run,
        "stages": {},
        "actions": [],
        "status": "RUNNING",
        "warnings": [],
    }
    try:
        disc = discover(repo_root=root)
        trace["stages"]["discover"] = {
            "status": "OK",
            "stale": len(disc["stale_products"]),
            "fresh": len(disc["fresh_products"]),
            "missing": len(disc["missing_products"]),
        }
        trace["warnings"].extend(disc.get("warnings", []))

        val = validate(repo_root=root)
        trace["stages"]["validate"] = {
            "status": "OK",
            "eval_files": len(val["eval_reports_found"]),
            "audit_files": len(val["audit_reports_found"]),
            "grade_summary": val["grade_summary"],
            "pages_needing_heal": len(val["pages_needing_heal"]),
        }
        trace["warnings"].extend(val.get("warnings", []))

        comp = compare(disc, val, repo_root=root)
        trace["stages"]["compare"] = {
            "status": comp["status"],
            "action_count": comp["action_count"],
            "backlog_status": comp["backlog_status"],
        }
        trace["actions"] = comp["actions"]
        trace["warnings"].extend(comp.get("warnings", []))

        gen = generate(comp, dry_run=dry_run, repo_root=root)
        trace["stages"]["generate"] = {
            "status": gen["status"],
            "run_id": gen["run_id"],
            "selected_action": gen["selected_action_type"],
            "prompt_path": gen.get("prompt_path"),
        }

        # Execute mode (MODE 5): write sprint prompt and HANDOFF.md
        if not dry_run:
            reports_sup = root / "reports" / "supervisor"
            reports_sup.mkdir(parents=True, exist_ok=True)

            # Write sprint prompt
            prompt_path = reports_sup / f"next-sprint-{run_id}.md"
            prompt_path.write_text(gen["prompt"], encoding="utf-8")
            trace["stages"]["generate"]["prompt_written_to"] = str(prompt_path)

            # Write HANDOFF.md — MODE 5 explicit execute, backlog/HANDOFF.md only
            handoff_path = root / "backlog" / "HANDOFF.md"
            handoff_path.parent.mkdir(parents=True, exist_ok=True)

            # Set final status before building handoff content
            if comp["status"] == "NO_ACTIONS_READY":
                trace["status"] = "NO_ACTIONS_READY"
            else:
                trace["status"] = "EXECUTE_COMPLETE"

            handoff_content = _build_handoff(trace, gen, comp, run_id, now, root)
            handoff_path.write_text(handoff_content, encoding="utf-8")
            trace["stages"]["handoff_write"] = {
                "status": "WRITTEN",
                "path": str(handoff_path),
            }
            prompt_path_for_sync = str(prompt_path)
        else:
            if comp["status"] == "NO_ACTIONS_READY":
                trace["status"] = "NO_ACTIONS_READY"
            else:
                trace["status"] = "DRY_RUN_COMPLETE"
            prompt_path_for_sync = None

        syn = sync(sprint_prompt_path=prompt_path_for_sync, repo_root=root,
                   write_to_disk=not dry_run)
        trace["stages"]["sync"] = {"status": syn["status"],
                                   "persisted": syn.get("persisted", False)}

        trace["completed_at"] = datetime.now(timezone.utc).isoformat()

        # Build dashboard (always — dry-run and execute)
        dashboard_content = _build_dashboard(trace, disc, val, comp, gen, syn, run_id, now, dry_run)
        trace["dashboard_content"] = dashboard_content

    except Exception as exc:
        trace["status"] = "FATAL_ERROR"
        trace["error"] = str(exc)
        trace["traceback"] = traceback.format_exc()
        return trace, 1

    return trace, 0


def main():
    parser = base_args("Master supervisor orchestration loop")
    args = parser.parse_args()
    dry_run = not args.execute

    trace, exit_code = orchestrate(dry_run=dry_run)

    reports_sup = Path(REPO_ROOT) / "reports" / "supervisor"
    reports_sup.mkdir(parents=True, exist_ok=True)
    run_path = reports_sup / f"run-{trace['run_id']}.json"

    # Write dashboard if produced
    dashboard_path = None
    if "dashboard_content" in trace:
        dashboard_path = reports_sup / f"dashboard-{trace['run_id']}.md"
        dashboard_path.write_text(trace.pop("dashboard_content"), encoding="utf-8")
        trace["dashboard_path"] = str(dashboard_path)

    run_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")

    if args.output:
        safe_emit(trace, args.output)
        print(f"Trace written to {args.output}")

    print(f"Status: {trace['status']} | Run: {trace['run_id']} | "
          f"Actions: {len(trace['actions'])} | Warnings: {len(trace['warnings'])}")
    if dashboard_path:
        print(f"Dashboard: {dashboard_path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
