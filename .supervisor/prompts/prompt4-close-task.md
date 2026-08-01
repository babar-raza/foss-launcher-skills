Close this task cleanly.

1. Review everything changed in this session.
2. Commit all completed changes. If the work spans clearly different change groups, use logically separated commits. Otherwise use one clean commit.
3. Update this mission's own plan file in place with the current final status. Amend it,
   do not overwrite history. `plans/master-plan.md` is a thin index only (mission ID ->
   file -> one-line status, per mission, restructured 2026-08-01 so unrelated concurrent
   sessions on unrelated missions never contend for one shared file) — do not write full
   mission content there.
   - If this mission already has a file: amend `plans/missions/{mission_id}.md` in place.
   - If this is a new mission with no file yet: create `plans/missions/{mission_id}.md`.
   - Either way, update (or add) this mission's one row in `plans/master-plan.md`'s index
     table to reflect its current status. Do this through
     `scripts/pipeline/lib/master_plan_index.py`'s `upsert_mission_row()` (lock-guarded
     read-modify-write), NOT a direct hand-edit of the index file — a bare edit can lose
     a concurrent session's update to a DIFFERENT mission's row (both read the file,
     both write back, whichever writes second silently erases the other's row). Example:
     ```
     PYTHONPATH=scripts/pipeline .venv/Scripts/python -c "
     from lib.master_plan_index import upsert_mission_row
     upsert_mission_row('plans/master-plan.md', '<mission_id>',
                         'plans/missions/<mission_id>.md', '**CLOSED**')"
     ```
   Record in the mission's own file:
   - what was completed
   - what changed
   - verification performed
   - any remaining follow-ups or non-blockers
4. Mark the task closed only if the implementation, verification, commit, and this
   mission's own plan file + index row are all complete.
5. In the final response, provide:
   - files changed
   - commit hash(es)
   - exact mission plan file (and index row) updated
   - closure status: CLOSED or NOT CLOSED

Rules:
- Do not claim closure without verifying the final repo state.
- Do not leave uncommitted relevant changes behind.
- Do not create ad hoc summary files unless required by governance.
- Prefer existing governed workflows and skills.
