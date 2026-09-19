# Shortcode-regression investigation — OUR OWN WORK (MT066 supervisor + lane agents)

**Date:** 2026-09-19
**Investigator:** read-only agent, isolated worktree. No writes to `content/`, `scripts/`,
`data/`, plans, or any git index outside a throwaway sandbox. No commits, no pushes.
**Scope:** only the work of this Claude session — supervisor session `bddfea15` plus its
~35 background lane agents, 2026-09-17 → 2026-09-19, mission
`MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION` (plus the MT071/MT069 commits the same
session made). A second investigator covers every other process.
**Evidence base:** frozen snapshot `evidence_snapshot/` (00..05) taken 2026-09-19T07:57:43Z;
`git log`/`git show`/`git diff` against `origin/main`; reflogs; a throwaway synthetic git
sandbox; direct reads of the tooling source.

---

## 1. Verdict

1. **No. Our committed content never replaced a shortcode with a hardcoded install
   command.** Across the 100 commits in `8b7f5d038f..origin/main` (the session range) the
   net shortcode change in `content/**/*.md` is **+1187 / −1**, and the single removal is
   a deliberate, correct de-duplication. Widening to the last 276 commits (back to
   2026-09-11) gives the same result: **1 shortcode removal, 0 cases of a literal being
   added to a file that already had a shortcode.**
2. **Yes, the stale-checkout effect is real, is ours, and is fully reproducible.** What
   the owner saw is a genuine, mechanical artifact of how lane agents commit: the main
   checkout's `HEAD` is advanced by a shared ref update while its `.git/index` and working
   tree are never updated, so `git diff --cached` in the main checkout shows exactly
   "shortcodes removed, literals added". Reproduced end to end in a sandbox (§4.4).
3. **The danger was real, not cosmetic.** A bare `git commit` from any session, at snapshot
   time, would have committed a byte-exact revert of 109 shortcode lines to 106 literal
   install commands across 51 paths.
4. **Two guard blind spots make this class of revert survivable rather than blocked**
   (§7): `git_plumb_commit.py`'s stale-file check silently suppresses `content/` findings
   unless the committing lane has a resolved session-ledger manifest, and the porcelain
   pre-commit Step 34 excludes `content/` from the stale guard entirely. Proven in the
   sandbox: the same silent revert is blocked with a manifest and **committed without
   one**.
5. **Residue is not confined to the main checkout.** 8 leftover worktrees currently hold
   **1,218 dirty `content/*.md` files, 420 of which would reintroduce a literal where
   `origin/main` has a shortcode** — including 321 `cells/python` files in one lane
   worktree and 98 blog files in a pre-existing non-agent worktree that also carries an
   unmerged commit (§8).

---

## 2. What I verified vs. inferred

| Claim | Status |
|---|---|
| Committed content shows no shortcode→literal regression | **Verified** — full per-file blob comparison over 276 commits |
| Main-checkout staleness mechanism | **Verified** — code citation + sandbox reproduction |
| `checkout_sync report` 200-row truncation | **Verified** — source line |
| WinError 206 source | **Partly verified** — measured this machine's real ceiling; could not determine which argv form the lane actually used |
| Lane stale-check blind spot | **Verified** — code citation + sandbox reproduction of both outcomes |
| Migrators cannot write a literal | **Verified** — source reading; both write only shortcode text |
| `locale_patch.py` can write a literal if the caller reverses the pair | **Verified** (structural); **it was never run** — 0 report directories under `reports/agents/locale-patch/` |
| Why only 51 residue paths survived rather than thousands | **Inferred**, corroborated by the plan's own wave-11 log (a manual hygiene sweep cleared 376 earlier entries) |
| Who advanced the lane branch refs with a bare `update-ref` | **Not determined** — the reflog entries carry no message (§8.2) |

---

## 3. Finding 1 — committed content is clean (the important one)

### 3.1 Method

A per-commit, per-file blob comparison (not a line-diff heuristic): for every commit in the
range, for every `content/**/*.md` it touched, the parent blob and the child blob were each
counted for

* shortcode occurrences — `{{<` or `{{%` followed by `package-install` / `package-install-inline`
* literal install commands — `pip install`, `python -m pip …`, `dotnet add package`,
  `Install-Package`, `<PackageReference`, `npm install|i|add`, `yarn add`, `pnpm add`,
  `go get`, `cargo add`, `nuget install`

and flagged `SC_DROP` (shortcode count fell) or `LIT_ADD_SC` (literal count rose in a file
that already had a shortcode).

### 3.2 Result — session range `8b7f5d038f..origin/main` (100 commits)

```
SC_DROP     : 1   (6b2068f11b, intentional — see 3.3)
LIT_ADD_SC  : 0
LIT_ADD     : 2   (new locale files, inherited English prose — see 3.4)
net shortcode delta across content/**/*.md : +1187 / -1
```

Per-commit shortcode totals for the migration commits (added/removed):

| Commit | + | − | Subject |
|---|---|---|---|
| `d766cda86d` | 357 | 0 | content(cells/python) migrate literal install commands to shortcode |
| `e63c268614` | 351 | 0 | content(3d/python) migrate literal install commands to shortcode |
| `ff3823892e` | 136 | 0 | content(3d/net) migrate inline install-command literals |
| `37f90dc426` | 106 | 0 | content(slides/net) migrate literal install commands to shortcode |
| `b85265ac0f` | 74 | 0 | content(email/net) migrate Install-Package/PackageReference literals |
| `7daee2ed12` | 69 | 0 | content(pdf/net) migrate PackageReference literals |
| `0891a73551` | 22 | 0 | fix(content) cells/go inline install mention |
| `3ac1bb59da` | 19 | 0 | content(cells/typescript) migrate literal install commands |
| `6b2068f11b` | 0 | **1** | fix(content) residual PyPI headings/pin + invented release-history claim |

### 3.3 The single shortcode removal — verified intentional and correct

`6b2068f11b` → `content/docs.aspose.org/en/tex/python/getting-started/installation.md`
removed a **duplicate** of the identical shortcode that sat under a meaningless
"To pin a specific version:" heading:

```
-### Install from PyPI
+### Install the Package
 Run the following command to install the latest version:
 {{< package-install "tex" "python" >}}
-To pin a specific version:
-{{< package-install "tex" "python" >}}
 ### Verify Installation
```

Both shortcodes rendered the *same* command, so the "pin a specific version" section was
factually wrong. One shortcode remains; **no literal was introduced**; the page reads
correctly after the edit.

The same commit's three `package-install-inline` → block `package-install` conversions were
also checked: each is shortcode-to-shortcode, count-preserving, and the resulting prose
reads correctly — e.g. `content/docs.aspose.org/en/html/python/_index.md:27-29` now reads
"Requires Python 3.10 or later. Pure Python — no browser engine or native dependencies.
Install it as follows:" followed by the block shortcode. Verified for all four files.

### 3.4 The two `LIT_ADD` findings — not shortcode replacements, but a real minor defect

`0c3e809f37` (a translation commit) created
`content/docs.aspose.org/{nl,pl}/barcode/python/getting-started/_index.md`. Each carries the
correct `{{< package-install "barcode" "python" >}}` **and** a prose bullet mentioning
`pip install` in running text — inherited verbatim from the English source as it stood at
that moment (`…/en/…/_index.md:113`).

A later MT066 commit (`3c5b8e804e`, TC-PKG-07-02) reworded that English bullet, but the
locale copies were not re-propagated. **Live drift today on `origin/main`:** `de`, `nl`,
`pl`, `sv` still carry the literal-mentioning bullet that English no longer has. Low
severity (prose mention, not a copy-pasteable command block), but it is a real
English→locale desync produced by our own sequencing, and it is invisible to
`install_defect_sweep.py`, which is English-source-only by construction
(`scripts/pipeline/commands/ops/install_defect_sweep.py` — `_english_source_file_rows()`,
"Scoped to locale == 'en' only").

### 3.5 Widened scan

Re-running over `origin/main~260..origin/main` (**276 commits**, back to `fc295e1521`,
2026-09-11) yields **the same single `SC_DROP` and zero `LIT_ADD_SC`**. The 107 `LIT_ADD`
rows are all brand-new locale translation files inheriting literals that already existed in
their English sources — never a shortcode being replaced.

---

## 4. Finding 2 — mechanism of the stale main checkout

### 4.1 Which repository does the post-commit sync operate on?

`scripts/pipeline/commands/ops/git_plumb_commit.py:112`

```python
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
```

`__file__` is `<checkout>/scripts/pipeline/commands/ops/git_plumb_commit.py`, so
`parents[4]` is **the checkout the script was invoked from** — for a lane agent, its own
worktree. `plumb_commit()` then does (line 1383):

```python
root = Path(repo_root) if repo_root is not None else _REPO_ROOT
```

and every `git` call in the whole sequence runs with `cwd=str(root)`:
`rev-parse HEAD` (1388), `read-tree` (1449), `add -f --pathspec-from-file` (1459),
`write-tree` (1549), `commit-tree` (1553), `update-ref` (1586), `push` (1602). Finally:

`git_plumb_commit.py:1679-1680`
```python
    if sync_state:
        _sync_local_state(head_sha, commit_sha, files, root=root)
```

and `_sync_local_state` (1017) calls
`checkout_sync.sync_after_ref_advance(..., repo_root=root, mode="index")`.

**`root` is the lane worktree. The main checkout is never a parameter of any of this.**
Confirmed live from this investigator's own worktree copy:

```
module _DEFAULT_REPO_ROOT (from this worktree's copy):
  …/.claude/worktrees/agent-a445d1cd75eb7f87f
```

### 4.2 Why the main checkout's HEAD moves anyway

`git_plumb_commit.py:1586`

```python
_git(["update-ref", f"refs/heads/{branch}", commit_sha, head_sha], repo_root=root)
```

`refs/heads/main` lives in the **shared** common git directory, not per-worktree. The main
checkout's `HEAD` is a symbolic ref to `refs/heads/main`, so this one command moves the main
checkout's HEAD from another worktree. Its `.git/index` (a per-worktree file — the main
checkout's own `.git/index`, distinct from `.git/worktrees/<lane>/index`) and its working
tree are untouched, and nothing in the tool ever looks at them.

Net state in the main checkout for every path such a commit touched:
`HEAD = new blob`, `index = old blob`, `worktree = old blob` → porcelain `M ` (staged),
and `git diff --cached` renders the migration **backwards**.

The compare-and-swap third argument (`head_sha`) is why this works at all: lanes first run
`git merge --ff-only origin/main` in their own worktree so their HEAD equals
`refs/heads/main`. Verified in the lane reflogs, e.g.

```
37f90dc426 worktree-agent-aeeb62095416b13f6@{2026-09-19 00:19:00}: merge origin/main: Fast-forward
8ab9d61e83 worktree-agent-aeeb62095416b13f6@{2026-09-19 00:16:36}: merge origin/main: Fast-forward
43c618b012 worktree-agent-aeeb62095416b13f6@{2026-09-18 23:51:24}: branch: Created from origin/main
```

### 4.3 Quantification

* Last porcelain `git commit` on `refs/heads/main`: `19c87db628`, **2026-09-11 23:59**.
  Last operation that refreshed the main checkout's index/worktree: a
  `pull --ff … : Fast-forward` at **2026-09-14 11:18** (`ec5a71f804`). Everything after that
  is a message-less `update-ref` — i.e. every main-branch advance for five days was plumbed.
* Session range touched **2,258 paths, 1,363 of them under `content/`**. Every one of those
  touched by a *lane-built* commit is a residue candidate in the main checkout.
* At snapshot time the surviving residue was **51 staged entries** across 4 commits:
  36 from `37f90dc426` (slides/net, all locales), 11 from `6b2068f11b`, 4 from
  `8ab9d61e83` / `374e6cf0fa` (governance scripts). The staged patch:
  **109 shortcode lines removed, 4 added, 106 literal install lines added, 0 removed.**
  Example (`evidence_snapshot/03_staged_content.patch:124-126`):

  ```
  -{{< package-install "slides" "net" >}}
  +Install-Package Aspose.Slides.Foss
  ```
* Earlier waves produced far more (the plan's own wave-11 log records **376 stale entries**
  after wave 2, +47 after TC-PKG-07-02); those were cleared by a manual hygiene sweep. The
  51 are simply everything committed *after* the last manual sweep. **Inferred**, but
  consistent with both the log and the observed commit list.

### 4.4 Sandbox reproduction (throwaway synthetic repo, no remote configured, `push=False`)

A synthetic repo with one `content/docs.aspose.org/en/demo/python/getting-started/installation.md`
containing a literal, plus two linked worktrees. Lane B rewrote the file to the shortcode
and called the **real** `plumb_commit()` with `repo_root=<laneB>`:

```
commit built: 488a9d6c289c  parent 4a5d1e7b0a9b
refs/heads/main now: 488a9d6c289c
MAIN checkout HEAD : 488a9d6c289c   <-- moved, nobody touched it
MAIN checkout index OID for the file: 13eade8c9e54
  blob at base commit                : 13eade8c9e54     <-- index == PRE-commit blob
  blob at new HEAD                   : b42586ea3d00
MAIN checkout on-disk content is literal: True

MAIN checkout `git status --porcelain`:
M  content/docs.aspose.org/en/demo/python/getting-started/installation.md

MAIN checkout `git diff --cached -U0`:
-{{< package-install "demo" "python" >}}
+```bash
+pip install aspose-demo==0.1.0
+```

LANE B index OID for the file: b42586ea3d00  (synced by checkout_sync -> equals new HEAD blob)
```

That is the owner's symptom, bit for bit, produced by the sanctioned tool used exactly as
documented.

---

## 5. Finding 3 — why `checkout_sync` under-reported, and where WinError 206 comes from

### 5.1 The 200-of-376 under-report is a hard truncation

`scripts/pipeline/commands/ops/checkout_sync.py:61`
```python
p_report.add_argument("--max", type=int, default=200)
```
`scripts/pipeline/lib/checkout_sync.py:299`
```python
paths = [p for p in (result.stdout or "").split("\0") if p][:max_entries]
```

`residue_report()` reads `git diff --cached --name-only -z`, which git emits **sorted**, then
truncates to the first 200. With 376 staged paths, the first 200 are all `content/…`, so
every `reports/plan_state/…` and `scripts/…` entry fell off the end. This exactly explains
"200 of 376, and none of the plan_state/scripts ones" — it is a display cap, not a detection
failure, and it prints no indication that it truncated.

Second, narrower blind spot: `residue_report()` only inspects paths that are already
`git diff --cached`-different. Residue whose index entry happens to match HEAD for an
unrelated reason is invisible — acceptable, but worth knowing.

### 5.2 WinError 206

`--paths` is `nargs="*"` (checkout_sync.py:49), so a manual caller must put every path on the
command line. Measured on this machine:

```
direct  approx_cmdline= 33113  ok=True
direct  approx_cmdline= 34118  ok=False  FileNotFoundError: [WinError 206] The filename or extension is too long
shell   approx_cmdline=  8591  ok=False  The command line is too long.
```

i.e. the real ceilings are ~32,767 chars for a direct `CreateProcessW` and 8,191 through
`cmd.exe`. For the 314 paths of `e63c268614` (3d/python): avg path length 65.2 chars,
**repo-relative** command line ≈ **21,049 chars** — under the direct ceiling but well over
the shell one; the same 314 paths as **absolute** lane-worktree paths (the worktree prefix
alone is ~81 chars) come to ≈ **46,000 chars**, comfortably past the direct ceiling and
producing precisely `[WinError 206]`.

**I could not determine which form the lane used** (no transcript available to this
investigator). Either way the cause is structural — argv — and the fix already exists and was
not used: `--paths-from <file>` (checkout_sync.py:52). `git_plumb_commit.py` itself never hits
this because it calls the library with a Python list; only the manual CLI path is exposed.
Internal git calls are chunked at `_CHUNK = 300` (lib/checkout_sync.py:45), which for these
paths is ≈19,950 chars — safe today, but only by ~40 %% margin, and the chunk size is a
count, not a byte budget.

---

## 6. Finding 4 — the migrators cannot write a literal; `locale_patch.py` can

### 6.1 `package_install_migrator.py` — safe and idempotent

It only rewrites a **fenced code block whose entire body is a single install command**
(`_block_is_sole_command`, line 172) or a sole `<PackageReference …/>` element
(`_block_is_sole_package_reference`, 186). The only text it ever writes is
`shortcode = f'{{{{< package-install "{family}" "{platform}" >}}}}'` (line 237). Run against an
already-migrated page there are no qualifying fenced blocks, `block_count == 0`, it returns
`NOOP_NO_MATCH` and **writes nothing** (259-261). It cannot produce a literal under any input.

### 6.2 `package_install_inline_migrator.py` — same

Only a single-backtick span whose entire content fullmatches an install command is replaced,
never inside a fenced block, never on a `_is_noise_line`, and the only text written is the
inline shortcode (line 166). Zero replacements → no write (191-193). Idempotent; cannot
produce a literal.

### 6.3 `locale_patch.py` — the one component that structurally *could*

Three real gaps, none of which fired (the module was **never run**: zero directories under
`reports/agents/locale-patch/`, and the MT066 ledger's own rows record
"locale_patch.py itself was not needed" / "is not applicable here"):

1. **No direction guard.** `apply_patch_to_file()` (line 142) applies whatever
   `(old_text, new_text)` the caller supplies. Nothing checks that `new_text` does not
   *remove* a shortcode or *add* a literal. A reversed pair would propagate literals into
   every locale copy, gated only by `is_english_source_ready()` (which checks the *English
   source's* representation, not the patch's direction) and the change budget.
2. **Bypasses the provenance write gate.** Line 173 is a bare
   `filepath.write_text(new_text, encoding="utf-8")` — not `safe_content_write()`, which both
   other migrators use and which raises `ProtectedPageError` for `auto_updatable: false`
   pages and restamps provenance/`content_hash`. `locale_patch.py` can therefore overwrite a
   human-protected locale page and leaves `content_hash` stale.
3. **Context check guards one occurrence, the write replaces all.** The 5-line proximity
   check (154-168) is satisfied by a single nearby occurrence, then line 171 does
   `text.replace(old, new)` across the whole file.

**Safety property that does hold:** `old_text` must match byte-identically, so a locale file
that already carries the shortcode can never be matched by a *literal* `old_text`. The only
literal-writing path is a caller-supplied reversed pair.

---

## 7. Finding 5 — the two-lane race, and where the stale-file guard is blind

### 7.1 How the tree is built

`plumb_commit()` reads the lane's `HEAD` (1388), `read-tree`s it into an **isolated temp
index** (1449), then stages the lane worktree's on-disk bytes for exactly `--files`:

```python
_git_indexed(["add", "-f", "--pathspec-from-file", _pathspec_path])   # line 1459
```

So the committed content is whatever is on the **lane's** disk. Two lanes editing the same
file cannot corrupt each other's index (that is what the isolation buys), but the later
lane's whole-file content wins for the paths it names.

### 7.2 The guard — and its `content/` hole

`plumb_commit()` (1468) calls
`slib.detect_regressions(files, baseline=…, mode="index", index_file=tmp_index_path, …)`
**without** passing `content_prefix_session_only`, so it takes the library default:

`scripts/pipeline/lib/stale_file_regression.py:401`
```python
content_prefix_session_only: bool = True,
```
`…/stale_file_regression.py:453-459`
```python
finding_class = "session" if _is_session_class(commit) else "lookback"
if content_prefix_session_only and path.startswith("content/") \
        and finding_class == "lookback":
    report.diagnostics.append(...)   # suppressed -- not even a WARN
    continue
```
and `_is_session_class()` (432-440) returns **False for every commit when
`baseline.session_sha is None`**, which is exactly the case when the committing checkout has
no resolvable session-ledger manifest.

Consequence: **a `content/` silent revert made from a lane with no session manifest is
neither blocked nor warned — it is dropped to a diagnostic line.**

The porcelain path has the mirror-image hole. `scripts/pre-commit-audit.sh:1549` feeds Step 34
only `"${staged_non_content_files[@]}"` — `content/` is excluded from the porcelain stale guard
altogether. (The standalone CLI does pass `content_prefix_session_only=False` —
`scripts/ci/checks/check_stale_file_regression.py:115` — so a *hand-run* check is stricter
than either automatic one.)

### 7.3 Sandbox proof of both outcomes

Lane A fast-forwarded to Lane B's shortcode commit, then wrote back its own pre-migration
copy of the same file and called `plumb_commit()`:

```
EXP-2a  lane WITH a resolved session manifest
  stale-check: base=4a5d1e7b0a9b source=lookback checked=1 intervening=1
  RESULT: BLOCKED -- PlumbCommitBlocked: ... look like a silent revert of a more recent commit

EXP-2b  same race, lane with NO session-ledger dir at all
  resolve_context -> status='no_ledger_dir' base_sha=None
  stale-check: base=4a5d1e7b0a9b source=lookback checked=1 intervening=1
  RESULT: NOT BLOCKED -- commit 72664a7b658d built and refs/heads/main advanced to it.
    content now at HEAD is literal: True
```

Same file, same race, same tool — the only difference is whether a session manifest exists.

### 7.4 How exposed were we, in fact?

`session_ledger._SESSION_DIR = _REPO_ROOT / "reports" / "session-state"` (line 122), and
`_REPO_ROOT` resolves to the lane worktree, so each lane needs its *own* manifest.
**32 of 37 lane worktrees have one** (all carrying the supervisor's session id
`bddfea15-…` with a `base_commit_sha` equal to main's tip at lane creation — e.g.
`agent-aeeb62095416b13f6` → `43c618b012`, matching its branch-creation reflog entry).
**5 lane worktrees have none**: `agent-a185a3cf13338ccbc`, `agent-a225e339a0d9a275b`,
`agent-a2ffeb1e0225a5517`, `agent-a9da93d57f368d6a5`, `agent-af9f8056b211b89ba`. Those five
sit at 2026-09-17 commits and, per §3, produced no content regression — so the hole was
**armed but never fired** in this session. It is luck, not design.

A second, softer protection also held: `PlumbCommitLedgerBlocked` (1414-1422) refuses to
commit a dirty path the session's ledger does not list. This fired in the sandbox before I
seeded `touched_files`, and it is a genuine second line of defence for the same class.

### 7.5 How close did the two-lane race actually come? Measured.

Of the **1,364** distinct `content/**/*.md` paths committed in the session range, only **21
were committed by more than one session commit**, and every one of those is a deliberate,
sequential follow-up by the same owner rather than a cross-lane collision:

```
3c5b8e804e -> 6b2068f11b   10 paths   TC-PKG-07-02  -> TC-PKG-07-02-FIX      (same grade lane)
9ff0acc2ff -> 3d2640297b    6 paths   same blog alias fix, re-landed
4e647e972e -> 676f9792ff    1 path    blog differentiation -> stale-alias cleanup
c374965166 -> 671f5fdf52    1 path    new post -> duplicate-post retirement
659ec99b52 -> cd44592fe0    1 path    same blog post, re-landed
cd44592fe0 -> 671f5fdf52    1 path    new post -> duplicate-post retirement
f7a2d81aec -> 671f5fdf52    1 path    new post -> duplicate-post retirement
86804e6b55 -> ca9c3acece    1 path    cells/go migration -> evidence.model_sha restore
```

The specific collision hypothesised in the brief — the grade-fix lane and the
`cells/typescript` migration lane both writing
`content/docs.aspose.org/en/cells/typescript/getting-started/installation.md` — **did not
happen**: `3ac1bb59da` (cells/typescript migration) touched only 19
`content/kb.aspose.org/*/cells/typescript/faq.md` files; that `installation.md` was touched
only by `3c5b8e804e` and `6b2068f11b`, which are the same grade lane's own two passes.

So the race in §7.3 was never *exercised* in this session. The `isolation: "worktree"` +
one-product-per-lane scoping in plan §14.2 did its job at the scheduling level. That is a
scope discipline, not a mechanical gate — which is why P1/P2 below still matter.

---

## 8. Finding 6 — residue in leftover worktrees (not previously recorded)

### 8.1 Inventory (39 worktrees scanned; only those with dirty content or unmerged commits shown)

| Worktree | HEAD | dirty `content/*.md` | would reintroduce a literal where `origin/main` has a shortcode | unmerged commits |
|---|---|---|---|---|
| `agent-a2ce82e81ef2f9090` | `d766cda86d` | 349 | **321** (all `cells/python`, all locales) | 0 |
| `blog-url-frontmatter-fix` | `aaa92b0bc5` | 701 | **98** (blog locale copies) | **1** (`aaa92b0bc5` "fix(maintenance): remediate blog URL collisions safely") |
| `agent-a6a2dee06618f43ea` | `9ba18556b5` | 1 | 1 (`content/docs.aspose.org/en/cells/go/_index.md`) | 0 |
| `agent-a33b381dfb4a1e99c` | `b5d9e2c642` | 52 | 0 | 0 |
| `agent-af4a595b7216fbb5f` | `94e3a2dfe3` | 47 | 0 | 0 |
| `agent-a4d252e82ff92bf75` | `c47e56659a` | 45 | 0 | 0 |
| `agent-a5c7dec428890165c` | `9ede5d88be` | 22 | 0 | 0 |
| `agent-add22cd8ac6b4d4eb` | `b564f11225` | 1 | 0 | 0 |
| **total** | | **1,218** | **420** | **1** |

Probe of one representative file in `agent-a2ce82e81ef2f9090`:

```
porcelain  : 'M  content/docs.aspose.org/de/cells/python/_index.md'
HEAD blob  : 3bccf143b2db      (shortcode -- same as origin/main)
index entry: a7e06c5d2b54      (pre-migration literal)
disk blob  : a7e06c5d2b54      (pre-migration literal)
disk line 31: Python 3.7 oder hoeher benoetigt. `pip install aspose-cells-foss`.Keine innere Abhaengigkeit.
```

**Risk:** any porcelain commit made from that worktree — even one staging a single unrelated
file — sweeps its whole stale index into history and reverts 321 `cells/python` pages to
literals. The wave-11 hygiene sweep repaired the *main* checkout's copy of this same residue;
nobody repaired the worktrees'.

`blog-url-frontmatter-fix` is a pre-existing, non-agent worktree carrying a real unmerged
commit; merging that branch as-is would land 98 blog files whose shortcodes `origin/main`
already has. It is outside this session's work but it lives in our repo and is the same
hazard class.

### 8.2 Where this residue comes from (and what I could not determine)

`.git/worktrees/agent-a2ce82e81ef2f9090/logs/HEAD` shows the branch advancing four times with
**empty reflog messages**:

```
0000…000 be25deeeed …  (creation)
be25deeeed be25deeeed … reset: moving to HEAD
be25deeeed fda85cca6e …          <- no message
fda85cca6e 9ba18556b5 …          <- no message
9ba18556b5 b61ab346a6 …          <- no message
b61ab346a6 d766cda86d …          <- no message
```

An empty reflog message means a bare `git update-ref`. `git merge --ff-only` and
`git checkout` always write one (and two other lanes' reflogs *do* show
`merge origin/main: Fast-forward`). So some component advanced this lane's branch ref without
touching its index or worktree — structurally the same bug as §4, one level down.
**It is not `git_plumb_commit.py`**, which only ever advances `refs/heads/<branch>` (default
`main`) and then syncs *its own* root. The most plausible actor is the harness's own
worktree-sync, but the reflog records no message and I have no transcript, so **I could not
determine this conclusively.**

---

## 9. Finding 7 — coverage map of the existing guards (where they are blind)

| Guard | Runs when | Catches a shortcode→literal regression? |
|---|---|---|
| `scripts/pipeline/audit/package_install_literal.py` (`verify_package_install_literals`) | pre-commit Step 2 via `commands/content/audit.py`; `install_defect_sweep.py`; `install_literal_sweep.py` | **Only one direction** — "a literal exists". A file that *loses* its shortcode and gains nothing passes. Also skipped entirely by `audit/runner.py:audit_files()` when `infer_product()` fails or `Knowledge(family, platform).available` is False (`knowledge/` is gitignored → always false in CI). |
| `scripts/ci/checks/check_install_recipe_safety_fails.py` | `.github/workflows/content-audit.yml` only | **Never runs.** That workflow is `on: pull_request` and is marked SUPERSEDED in its own header ("this repo's real production path is direct push to main … it has never actually run against a real content change"). It also runs only `_verify_publish_channel_claims` / `_verify_no_unpublished_disclosure`, never `_verify_install_accuracy`. |
| `scripts/pre-commit-audit.sh` | every porcelain commit; also inside `git_plumb_commit.py` against the temp index | **No install-literal or shortcode-count step exists at all** (grep for `package-install`/`install` across the script returns only unrelated matches at lines 591, 889, 1401). |
| Step 34 stale-file regression | porcelain pre-commit | `content/` paths are **excluded** (`staged_non_content_files`, line 1549). |
| `plumb_commit()` stale check | every plumbed commit | `content/` findings suppressed unless session-class (§7.2). |
| `install_defect_sweep.py` | manual / taskcard acceptance | **English-source only** by construction; locale copies invisible. |
| `.github/workflows/content-governance-checks.yml` (the live push-triggered one) | every push | No install/shortcode step among its ~30 checks. |

**Net:** there is currently **no mechanical gate anywhere** — hook, CI, or tool — that fails
when a commit reduces a file's shortcode count or adds a literal install command where the
parent had a shortcode.

---

## 10. Finding 8 — process weaknesses in our own execution schema

Reading the mission plan's §14 (Execution Mechanism) and Execution Log:

1. **The spawn recipe never mentions index hygiene.** §14.3 says only "Land it via
   `git_plumb_commit.py` per this repo's own CLAUDE.md procedure (never bare `git commit`),
   citing `--skills` and `--plan`." Nothing instructs the lane to sync, or even check, the
   main checkout afterwards — and nothing could, because the tool takes no such parameter.
2. **The identical bug class was found and fixed only for one artifact.** §14.9 records the
   wave-1 discovery that `reports/plan_state/**` is worktree-local and made
   `TaskcardStore(repo_root=<main checkout>)` binding on every spawn. The git **index** is the
   same "worktree-local state the main checkout does not see" problem, and the generalisation
   was not made.
3. **Hygiene is a post-hoc manual ritual.** Wave 11's own log makes it a "standing rule from
   here: after every wave, (a) run the residue classifier and restore …". A manual per-wave
   step cannot bound the exposure window, and it left the 51 paths that the owner saw.
4. **The mission's acceptance criterion is one-directional.** TC-PKG-02's objective is
   "`verify_package_install_literals()` reaches 0 FAIL for each of the 19 products" and its
   parent acceptance is "`install_defect_sweep.py --check` shows 0 findings". Nothing in the
   taskcard ever asserts *shortcodes were gained* or *none were lost*. The whole mission was
   graded by a detector that is structurally incapable of seeing the regression the owner
   feared.
5. **The correction ladder (§14.6) has no row for content-direction regressions.** It covers
   silence, repeated failures, weakened tests, wrong spawn config, and out-of-scope paths —
   not "a lane's diff moved content the wrong way".
6. **The mechanism was already known and left unfiled.** Wave 11's log lists, under "Newly
   found, **not yet filed as taskcards/backlog**": "(c) `git_plumb_commit.py` runs its
   post-commit sync against the *committing worktree*, never the main checkout, so every
   worktree-lane commit leaves main-checkout index residue by construction". This
   investigation confirms that entry and adds the lane-worktree half (§8) and the
   `content/` guard hole (§7).

---

## 11. How to prevent it — ranked

Ranked by (risk removed ÷ effort). Nothing below was implemented.

### P0 — `git_plumb_commit.py` must not be able to leave another checkout stale
**Effort:** small (~40 lines + tests). **Risk:** low; additive.
Resolve the git **common dir** (`git rev-parse --git-common-dir`), enumerate every worktree
(`git worktree list --porcelain`), and after a successful ref advance run the existing
`checkout_sync.sync_after_ref_advance(..., mode="index")` **once per worktree whose HEAD
resolves to the advanced branch, plus the main checkout**, for exactly the committed paths.
The safety contract already covers this: each path is only touched when its index blob
provably equals `old_head:path`, so nothing uncommitted is ever clobbered. If any checkout
cannot be synced (index.lock held), print a loud, named warning listing the paths left stale —
the tool must never silently exit having created residue. This single change removes the
owner's entire symptom class, in the main checkout *and* in every lane worktree (§8).

### P1 — a real mechanical shortcode-regression gate
**Effort:** medium (~150 lines + tests + wiring). **Risk:** low.
A new `scripts/ci/checks/check_install_shortcode_regression.py` that, for every staged/
committed `content/**/*.md`, compares **parent blob vs proposed blob** and FAILs when
(a) the `package-install`/`package-install-inline` occurrence count decreased, or
(b) a literal install command count increased while the parent had ≥1 shortcode.
Requirements the existing guards miss and this must have:
* **all locales**, not English-only — the 36 `slides/net` locale files in the residue are
  exactly the population the current English-only sweep cannot see;
* **no dependency on `knowledge/`** (gitignored ⇒ `audit_files()` silently skips in CI);
* an allowlist keyed to an explicit override token for legitimate removals like
  `6b2068f11b`'s duplicate-shortcode cleanup.
Wire it into (i) `scripts/pre-commit-audit.sh` (so it also runs inside `git_plumb_commit.py`'s
Tier-1 pass against the temp index) and (ii)
`.github/workflows/content-governance-checks.yml`, which is the live push-triggered
workflow — **not** `content-audit.yml`, which never runs.

### P2 — close the `content/` hole in the stale-file guard
**Effort:** small. **Risk:** medium (could newly block commits — soak it as WARN first).
Two independent changes:
* `git_plumb_commit.py:1468` should pass `content_prefix_session_only=False` (matching what
  `check_stale_file_regression.py:115` already does) so a `content/` revert at least WARNs
  when the committing checkout has no session manifest;
* make a missing session-ledger manifest **loud** at `plumb_commit()` entry — today
  `status="no_ledger_dir"` passes silently and downgrades every finding.
Also make lane bootstrap create the manifest unconditionally, so the guard is armed by
construction rather than by 32-of-37 luck.

### P3 — fix `checkout_sync`'s reporting and argv fragility
**Effort:** small. **Risk:** none.
* `residue_report()` must state when it truncated (`--max`), and `report` should default to
  unlimited or print `showing N of M`.
* Make `--paths-from` the documented path in CLAUDE.md for any list above ~200 entries, and
  have the CLI auto-spill `--paths` to a temp file rather than relying on the caller.
* Replace `_CHUNK = 300` with a byte-budgeted chunker (target ≤ 24,000 chars/argv) so long
  locale paths cannot silently approach the ceiling.
* Add `checkout_sync.py report --all-worktrees`.

### P4 — lane-prompt and plan rules
**Effort:** trivial. **Risk:** none.
Add to §14.3's spawn recipe and §14.6's correction ladder:
* "Your commit must not reduce any file's `package-install` shortcode count or add a literal
  install command. Quote the before/after shortcode counts for every file you touch in your
  final report." (Makes the §14.8 "no partial credit" rule bite on this dimension.)
* "After your commit, report the tool's `checkout_sync:` summary line verbatim; if it reports
  anything other than all your paths synced, say so explicitly."
* A correction-ladder row: "a lane's diff reduces a file's shortcode count or adds a literal
  install command → refuse the result".
* Generalise §14.9: *any* state that is per-worktree (`reports/plan_state/**`,
  `reports/session-state/**`, **and the git index**) must be explicitly reconciled with the
  main checkout, not assumed shared.

### P5 — `locale_patch.py` hardening (pre-emptive; it has never been run)
**Effort:** small. **Risk:** none.
* Refuse any patch whose `new_text` removes a `package-install*` shortcode or introduces a
  literal install command, unless `--force` with a logged reason.
* Replace the bare `write_text` (line 173) with `safe_content_write()` so `ProtectedPageError`
  and provenance restamping apply, as they already do in both sibling migrators.
* Make the `context` proximity check gate the *specific* occurrence it validated instead of
  letting `str.replace` rewrite all of them.

### P6 — worktree lifecycle hygiene
**Effort:** small. **Risk:** low.
39 worktrees exist, 8 of them holding 1,218 dirty content files. Prune finished lane
worktrees (they are auto-cleaned only if unchanged), and have `/session-start` print
`checkout_sync.py report` **for every worktree**, not just the current one.

### P7 — repair the locale drift this mission created
**Effort:** trivial. **Risk:** none.
Re-propagate `3c5b8e804e`'s English rewording to `de`/`nl`/`pl`/`sv`
`barcode/python/getting-started/_index.md` (§3.4), and consider extending
`install_defect_sweep.py` beyond English-source scope — the plan's own wave-11 log already
lists this as unfiled finding (d).

---

## 12. What I could not determine

1. **Which argv form produced WinError 206.** I measured the real ceilings on this machine and
   showed 314 repo-relative paths (~21 KB) are under the direct limit while the absolute-path
   form (~46 KB) is over it — but the lane's actual command line is not available to me.
2. **Which component advanced the lane branch refs with a message-less `update-ref`** (§8.2).
   It is demonstrably not `git_plumb_commit.py`; the reflog records no actor and I have no
   lane transcripts.
3. **Exactly when the earlier 376-entry residue was cleared**, and therefore the precise
   per-commit residue history. I can show the surviving 51 map to the 4 most recent
   lane-built commits and that the plan's wave-11 log describes a manual restore; I did not
   reconstruct the intermediate index states.
4. **Whether any of the 5 manifest-less lane worktrees ever ran `plumb_commit()` on a
   `content/` path.** Their HEADs sit at 2026-09-17 commits and the committed-content audit is
   clean, so no regression resulted — but I could not enumerate their tool invocations.
5. **`blog-url-frontmatter-fix`'s unmerged commit** — I established that merging it as-is
   would land 98 files whose shortcodes `origin/main` already has, but its provenance and
   intent belong to another process and were out of scope here.

---

## Appendix — commands and artifacts used

* Per-commit blob audit: a throwaway script comparing `git show <rev>:<path>` blobs for every
  `content/**/*.md` in `8b7f5d038f..origin/main` and `origin/main~260..origin/main`.
* Frozen symptom evidence: `evidence_snapshot/00_summary.txt` … `05_worktrees.txt`.
* Reflogs: `git reflog show refs/heads/main`, per-lane branch reflogs,
  `.git/worktrees/<lane>/logs/HEAD`, `.git/logs/HEAD`.
* Sandbox: synthetic repo + two linked worktrees, no remote configured, `push=False`,
  driving the real `plumb_commit()`; deleted-on-demand, never touched the real repo.
* Worktree scan: per-worktree `git status --porcelain -- content` compared against
  `origin/main` blobs for shortcode/literal counts.
