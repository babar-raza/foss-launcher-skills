---
name: independent-content-review
id: S-127
description: >
  Content goes live the moment it is published.
---

# S-127: Independent Content Review — Author-Separated Verification Panel

<!-- CONTRACT: agent-executed
     purpose: the Independent Verification Panel (IVP). Every new or changed page is verified to
              production-website standard by fresh read-only reviewer agents who did not write it,
              before publication. S-90 stays the author-side gate; this skill supplies the
              independence S-90 does not claim.
     preconditions: the pages are final from the authors' side (S-23 content-check PASS, S-90 done);
                    docs/reference/production-page-rubric.md exists; the pinned Hugo runtime resolves
                    (scripts/ci/hooks/find_hugo.sh); for code pages the product artifact is
                    resolvable (S-126 artifact.json, or the published artifact)
     postcondition: reports/ivp/{family}/{platform}/{run}/ holds calibration.json, rendered_audit.json,
                    tiers.json, hash-bound verdicts/*.json, gate.json and panel_report.md; the cleared
                    page list is exactly the pages with the required PASS verdicts bound to their
                    CURRENT content sha256
     forbidden: editing any reviewed page; reviewers holding write tools; an author acting as
                reviewer; clearing a finding any way other than a re-review of the changed hash;
                writing under content/ or knowledge/
     idempotent: yes for the gate (a function of the page bytes and the verdict files); re-running
                 the panel on unchanged pages reuses valid verdicts and only spawns missing reviews
     verified: 2026-10-07
     id: S-127
     depends_on: [S-23, S-90]
-->

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} --pages FILE [--tier-policy default|dual-all] [--run-id ID] [--ledger PATH]`

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `{family} {platform}` | Yes | The product under review (used for the run directory and the artifact lookup). |
| `--pages FILE` | Yes | One repo-relative content path per line (`#` comments allowed): every new or changed page of the run. |
| `--tier-policy` | No | `default`: tier by AGENTS.md §7b triggers (every blog post and every page with code, format tables or capability claims is Tier-1, as is any Products page edit that changes capability or placement text). `dual-all`: two reviewers for every page. |
| `--run-id ID` | No | Defaults to `ivp-{UTC date}-{short git SHA}`. |
| `--ledger PATH` | No | A capability ledger for the run. When given, rubric check R7 applies. |

## Purpose

Verify every new or changed page to production-website standard with fresh read-only reviewers who did not write it, before publication.

Content goes live the moment it is published. S-90 (`/publish-readiness-review`) is run by the session
that authored the content and routes fixes itself, so it is a gate, not independence. This skill adds
a panel of reviewers with no shared context with the authors or with each other. They check each page
the way a careful person would, by running things, and they write verdicts bound to the exact bytes
they reviewed. The standard they apply is `docs/reference/production-page-rubric.md` (checks R1-R7).

Authors never clear findings. The only way a failed page gets cleared is a changed page and a fresh
review.

## Pre-conditions

1. `--pages` exists and every listed file exists. A missing file is a stop.
2. Knowledge is bootstrapped (`/knowledge-bootstrap` gate: `knowledge/{family}/{platform}/merged/` exists), so reviewers can check counts and claims against the model (R1.5). The rubric file exists; record its sha256 in `run.json`.
3. For pages with code: the artifact record from S-126 (`reports/example_verification/{family}/{platform}/*/artifact.json`) or the published artifact coordinates. If none can be found, say so in the run record; R2 reviews will report `BLOCKED_ARTIFACT` and the page cannot clear.
4. The invoking session did not author the pages, or it spawns the reviewers as separate agents (it always does; the invoking session only orchestrates and never reviews).
5. Skill context gate:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-127 --scope "reports/ivp/*"
   ```

## Steps

Run directory used below: `RUN=reports/ivp/{family}/{platform}/{run}`. Create `$RUN/verdicts` and keep `run.json` (run id, base SHA, rubric sha256, reviewer prompt sha256, author ids, artifact record, tool versions).

### 1. Calibrate before judging real pages

The panel is trusted only after it has caught every seeded defect on a canary page. Calibration is valid for a run if the rubric sha256 and the reviewer prompt sha256 are unchanged since the last passing `calibration.json`; otherwise redo it.

1. **Build the canary** from a real, clean page of the same site (copy it to `$RUN/canaries/canary_page.md`; never edit under `content/`). Seed one defect per row of the table in the rubric's Calibration section (D1-D10 or at least eight, covering R1.1, R1.4, R2.1, R2.4, R3.1, R3.6, R3.8, R4.1, R4.4). Apply each defect with a plain text edit, assert each edit changed the text, and write the answer key to `$RUN/canaries/ANSWER_KEY.json` (`{id, rubric_check, description}`). The key is never shown to reviewers. Give reviewers only the canary path and its sha256.
2. **Review the canary** with two fresh reviewers using the same prompt as for real pages (Step 4). Each writes a verdict for the canary into `$RUN/canaries/verdicts/`.
3. **Score**: a defect counts as caught by a reviewer when one of its findings has the defect's rubric check id and its evidence quotes or locates the seeded text. Write `calibration.json`: per defect, per reviewer, caught or missed, plus the rubric and prompt hashes.
4. **Gate**: every reviewer must catch every seeded defect. Any miss means: fix the rubric wording or the reviewer prompt, record the change, and re-run calibration with fresh reviewers. A miss that repeats after a fix is a systemic gap; stop and open a hardening card (`/pipeline-harden`, S-99) rather than reviewing real pages with an unreliable panel.

Reviewers also report genuine defects they find in the clean base page while calibrating; file those as findings for the owning content, not as calibration misses.

### 2. Build the affected site section to a temp directory

Group the pages by site (the directory under `content/`) and build each affected site with the pinned runtime. `hugo_temp_build.sh` removes its temp directory on exit, so the review snapshot is copied out inside `--exec`.

```bash
export RUN=reports/ivp/{family}/{platform}/{run}    # exported so the --exec shell sees it
HUGO_ENVIRONMENT=production bash scripts/ci/hooks/hugo_temp_build.sh \
  --config configs/<site>.toml \
  --exec 'mkdir -p "$RUN/rendered/<site>" && cp -r "$HUGO_OUT"/. "$RUN/rendered/<site>/"'
```

(`configs/blog.aspose.org.yml` for the blog.) Use the repo's pinned Hugo (`find_hugo.sh`, currently `0.154.5-extended_withdeploy`). Production environment matters: the evidence panel only renders in non-production builds, so a leak of it into this build is a real finding. For a very large site (reference) copy only the review set's directories plus `sitemap.xml` and the shared asset folders instead of the whole tree. If no Hugo binary resolves, rendered checks are `NOT_RUNNABLE_LOCALLY` and no page can clear.

Derive each page's URL path from the built output. An English page `content/<site>/en/<path>.md` is normally served at `/<path>/` (no `/en/`); blog content has no language folder; a frontmatter `url:` or `slug:` overrides the path. Confirm that the built `index.html` exists. A page that did not build is a blocker. Write the URL list to `$RUN/urls.txt` and the page-to-URL map to `$RUN/page_urls.json`.

### 3. Run the deterministic audit

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/content/rendered_page_audit.py \
  --build-dir "$RUN/rendered/<site>" --pages-file "$RUN/urls.txt" \
  --md-source-root content/<site> --site-base-url https://<site-host> \
  --external-links head --json-out "$RUN/rendered_audit.json" --fail-on none
```

`--external-links head` is rate-limited and cached; add an allowlist file (`--external-allowlist`) for hosts that must never be fetched. The audit covers R3.x, R4.1, R4.4, R2.4 and R6.5 mechanically. It feeds the reviewers. It never replaces them, and a clean audit does not clear a page.

### 4. Spawn the reviewers

Compute tiers deterministically and write `$RUN/tiers.json` (`{page: 1|2|3}`) from `--tier-policy`. Every reviewer is a fresh agent that:

- has read-only tools (no Edit/Write): for example the `Explore` agent type, which can run Bash for compiling and `javap`/grep but cannot change repo files; scratch work goes in a fresh temp directory it creates itself;
- gets no author context, no other reviewer's output, and no ledger verdicts;
- gets exactly: the page path and its current sha256, the rubric path, the verdict schema, the rendered snapshot path and `rendered_audit.json` entry for that page, the pinned SHA / artifact path with its sha256, the declared diff scope and base SHA (for R5), and the instruction below.

Reviewer prompt (store it as `$RUN/reviewer_prompt.md` and record its sha256):

> You are an independent reviewer. You did not write this page and must not edit anything. Apply every check R1-R6 in `docs/reference/production-page-rubric.md` (R7 only if a ledger path is given) to the page, by running commands and recording each command and where its output is. Compile and run every code block yourself in a clean scratch directory against the product artifact (verify the artifact's sha256 first); do not trust any ledger for pass or fail. Read the rendered HTML, not just the Markdown. Check names and claims against the source at the pinned SHA or `javap` of the artifact. Check `git diff --name-only <base>` against the declared scope. Return ONLY the verdict JSON in the rubric's schema, with `content_sha256` equal to the hash you were given (re-hash the file yourself and stop if it differs). A check you cannot run is FAIL with the reason, never PASS. An NA needs a stated reason.

**Panel size**: Tier-1 pages get two reviewers (distinct agents, spawned separately, never shown each other's output); Tier-2/3 pages get one. A disagreement between reviewers, or a blocker from any reviewer, adds a third fresh reviewer whose job is to reproduce or refute each finding with evidence. Either way, a blocker at the current hash sends the page to `REWORK_REQUIRED` (Step 6); the third review informs the fix, it does not clear the blocker.

**Storing verdicts**: the orchestrator saves each reviewer's returned JSON byte-for-byte as `$RUN/verdicts/<reviewer_id>-<page-slug>.json`. It never edits a verdict and never fills in a missing field. A verdict that fails to parse or lacks fields is discarded and that review is re-run with a fresh reviewer.

### 5. Sampling policy for mechanically generated reference changes

Reference pages are produced by the generator, so thousands can change in one run. Review them in three layers (the full policy is in the rubric):

1. **100% by reviewers**: every NEW reference page for a capability unit, and every page whose body changed beyond an evidence-only restamp. Take the classes from the run's `page_decisions.jsonl` (`BODY_UPDATED`, `GENERATED`) cross-checked with `git diff` against the base SHA.
2. **100% deterministically**: every remaining changed page. Verify with git that only `evidence.*` or automatic fields changed, that no body lines were deleted, and run `rendered_page_audit.py` over the whole set (`--fail-on blocker`).
3. **Seeded sample**: at least 5% (minimum 25) of the evidence-only or regenerated-unchanged pages, chosen with `random.Random(int(sha256(run_id).hexdigest(), 16))` over the sorted page list. Record the seed and the chosen list in `$RUN/sample.json`. A defect found in the sample doubles the sample size; a defect that reflects the generator rather than one page is systemic: open a hardening card (S-99) and re-run the affected class after the fix.

Docs, KB, blog and Products pages are never sampled. Each gets its full review.

### 6. The gate

A page is cleared only when, bound to its CURRENT content sha256 (LF-normalised bytes), it has the required number of valid PASS verdicts from distinct reviewers who are not authors, and no FAIL verdict or blocker finding exists at that hash. A verdict for any earlier hash is ignored: an edit after review invalidates it. Any blocker overrides every PASS. There is no way to clear a finding except a changed page and a fresh review.

Run the gate from the repo root (it reads `tiers.json` and `verdicts/`, writes `gate.json`, and exits 0 only when every listed page is cleared; pass the comma-separated author ids as the third argument):

```bash
.venv/Scripts/python - "$RUN" "<pages file>" "<author ids>" <<'PY'
import hashlib, json, sys
from pathlib import Path

run_dir, pages_file = Path(sys.argv[1]), Path(sys.argv[2])
authors = {a for a in (sys.argv[3].split(",") if len(sys.argv) > 3 else []) if a}
tiers = json.loads((run_dir / "tiers.json").read_text(encoding="utf-8"))
pages = [p.strip() for p in pages_file.read_text(encoding="utf-8").splitlines()
         if p.strip() and not p.startswith("#")]
DIMS = ("R1", "R2", "R3", "R4", "R5", "R6")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()

def valid(v):
    for k in ("page", "content_sha256", "reviewer_id", "tier", "checks", "findings", "verdict"):
        if k not in v:
            return False, f"missing key {k}"
    if v["reviewer_id"] in authors:
        return False, "reviewer is an author"
    if v["verdict"] == "PASS":
        if any(f.get("severity") in ("blocker", "major") for f in v["findings"]):
            return False, "PASS with blocker/major finding"
        if any(c.get("result") not in ("PASS", "NA") for c in v["checks"]):
            return False, "PASS with a failed check"
        if any(c.get("result") == "NA" and not str(c.get("note", "")).strip() for c in v["checks"]):
            return False, "NA without a note"
        seen = {str(c.get("id", ""))[:2] for c in v["checks"]}
        if not all(d in seen for d in DIMS):
            return False, "dimension missing: " + ",".join(d for d in DIMS if d not in seen)
    return True, ""

verdicts = {}
for f in sorted((run_dir / "verdicts").glob("*.json")):
    v = json.loads(f.read_text(encoding="utf-8"))
    verdicts.setdefault(v.get("page"), []).append((f.name, v))

report, cleared = [], []
for page in pages:
    need = 2 if int(tiers.get(page, 1)) == 1 else 1
    cur = sha(page) if Path(page).is_file() else None
    row = {"page": page, "tier": tiers.get(page, 1), "need": need, "sha256": cur, "status": "", "why": []}
    passes, blocked = {}, False
    for name, v in verdicts.get(page, []):
        if v.get("content_sha256") != cur:
            row["why"].append(f"{name}: stale hash (ignored)")
            continue
        good, why = valid(v)
        if not good:
            row["why"].append(f"{name}: invalid ({why})")
        if v.get("verdict") == "FAIL" or any(x.get("severity") == "blocker" for x in v.get("findings", [])):
            blocked = True
            row["why"].append(f"{name}: FAIL or blocker at current hash")
        elif good:
            passes[v["reviewer_id"]] = name
    if cur is None:
        row["status"] = "MISSING_PAGE"
    elif blocked:
        row["status"] = "REWORK_REQUIRED"
    elif len(passes) >= need:
        row["status"] = "CLEARED"
        cleared.append(page)
    else:
        row["status"] = "NEEDS_REVIEW"
        row["why"].append(f"{len(passes)}/{need} independent PASS verdicts at current hash")
    report.append(row)

out = {"pages": report, "cleared": cleared, "all_cleared": len(cleared) == len(pages)}
(run_dir / "gate.json").write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
for r in report:
    print(f"{r['status']:16} tier{r['tier']} {r['page']}  {'; '.join(r['why'])}")
print("ALL_CLEARED" if out["all_cleared"] else "NOT_CLEARED")
sys.exit(0 if out["all_cleared"] else 1)
PY
```

`REWORK_REQUIRED` and `NEEDS_REVIEW` pages go back to the owning author skill (S-20, S-56, S-57, S-58, S-73, or the refresh run for generated pages) with the findings. After the fix the page has a new hash, the old verdicts no longer count, and Steps 2-6 run again for that page with fresh reviewers (reviewers from the failed round are not reused).

### 7. Panel report

Write `$RUN/panel_report.md`: calibration result, tier counts, reviewer count, per-page status from `gate.json`, every finding with severity and owner (`skill`, `script` or `content`), the sampling seed and list for reference changes, the audit summary, and the final cleared list. Findings classed `script` or `skill` that recur are systemic; file them for `/pipeline-harden`.

Output to the caller: the panel report path and the list of cleared pages (`gate.json` `cleared`), with the count not cleared.

### 8. Close

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-127 --status completed
```

## Post-conditions

- `gate.json` lists every page in `--pages` with a status; nothing is cleared without the required valid verdicts at its current hash.
- No reviewed page, content file or knowledge file was modified by this skill.
- Calibration is recorded and bound to the rubric and prompt hashes in force.

## Escalation

- S-23 FAIL persisting after author fixes, grade F after the author skills' retries, or any legal, license or business claim needing outside verification: stop and escalate per AGENTS.md §8 (§7c defines when a real person is needed; everything else is decided here).
- A canary the panel cannot fully catch after one rubric/prompt fix: stop; do not review real pages.

## Error handling

| Condition | Result | Action |
|---|---|---|
| No pinned Hugo runtime | Rendered checks `NOT_RUNNABLE_LOCALLY` | Page cannot clear. Never pass R3 on assumption. |
| Page did not build (no output file) | Blocker | Return to the author skill; check `url:`/`slug:` and draft state. |
| Product artifact missing | R2 `BLOCKED_ARTIFACT` | Page with code cannot clear until S-126 or the published artifact supplies one. |
| Reviewer verdict malformed or hash mismatch | Discarded | Re-run that review with a fresh reviewer. |
| Reviewer disagrees with another on a Tier-1 page | Third reviewer + `REWORK_REQUIRED` | Third reproduces or refutes with evidence; blockers still need a changed page. |
| Calibration miss | Panel untrusted | Fix prompt or rubric, re-calibrate with fresh reviewers. |
| Author id appears as a reviewer id | Verdict invalid | Discard; spawn a fresh reviewer. |

## Composition

Downstream of the content skills and their author-side gates (S-23, S-90) and of S-126 (examples).
Upstream of `capability_surface_gate.py` (the close step of S-84), which should only be run once this
panel's gate shows every page of the run cleared. Reviewers re-derive facts independently; they use the
S-126 hand-off only as provenance.
