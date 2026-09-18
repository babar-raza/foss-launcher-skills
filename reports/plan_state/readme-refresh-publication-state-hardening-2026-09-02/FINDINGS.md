# readme-refresh publication-state hardening — findings and design (living spec)

Mission `readme-refresh-publication-state-hardening-2026-09-02`. Trigger: user question
(2026-09-02) — 3d/python was published to PyPI; does S-120 detect that during regeneration, and
does it enhance the candidate accordingly? Harden the skill for the general case, then regenerate
3d/python with the hardened skill for verification and manual review.

## 1. Investigation (all re-verified live 2026-09-02)

### The publication itself
- PyPI `aspose-3d-foss` **26.1.0**, one file: `aspose_3d_foss-26.1.0-py3-none-any.whl`, uploaded
  2026-08-29T04:13:26Z. No sdist. `requires_python >=3.7`. `evidence/investigation/pypi.aspose-3d-foss.json`.
- Wheel contents == repo HEAD `d9f3bfe` (2026-08-29, "Merge remote-tracking branch 'origin/master'"):
  358/358 `.py` files byte-identical modulo CRLF. The published artifact IS the tree the README documents.
- Publishing commit `92ba9c24` ("Changes for deploying to pypi.org") added `.github/workflows/publish.yml`
  (release-triggered, sdist+wheel, twine check, tag==version guard) and `docs/releasing.md`; its only
  `setup.py` change is a classifier string. No git tag and no GitHub Release exist → 26.1.0 was uploaded
  manually (consistent with releasing.md's "publish the first release manually once").
- **Metadata defects in the published package** (upstream issues, never README content):
  - `Home-page` / `project_urls.Homepage` = `https://github.com/aspose-3d/Aspose.3D-for-Python` → HTTP 404;
    the real repo is `aspose-3d-foss/Aspose.3D-FOSS-for-Python` (setup.py `url=` is wrong).
  - No `License` / `License-Expression` metadata (repo has an MIT LICENSE file).
  - Wheel only, no sdist (the workflow would build both; the manual upload did not).
  - `docs/releasing.md` names the trusted-publisher owner/repo as `aspose-3d` / `Aspose.3D-for-Python`
    — not this repository; the next workflow-driven release will fail PEP 740 verification as documented.
- **Name-collision trap**: PyPI `aspose-3d` (26.8.0, 49 releases) is the commercial Aspose.3D for Python
  via .NET. Any probe that guesses names from the family is wrong; only the manifest-declared name
  (`setup.py name=`) may be used.

### The skill
- `_detect_install_info` (readme_refresh_run.py:1703) reads `data/package_registry.json` only.
  3d/python entry: `published: false`, `verified_at 2026-08-01`, method `pypi-backfill-scan`.
  There is no live registry call anywhere in S-120.
- Consumers of that flag: `_detect_available_badges` (PyPI version + pyversions badges), the verify-examples
  runner's `_acquire_python_environment` (pip from PyPI vs `pip install -e` clone), and
  `check_installation_matches_package_registry` — **advisory since 2026-08-12 (TC-HARDEN-32) because the
  registry was found stale in both directions** (words/net published on NuGet but recorded false; email/net
  casing). The docstring documents the unreliability and lowers the tier instead of fixing the source.
- Net effect for 3d/python today: `plan` would say unpublished; the composed Installation keeps "A PyPI
  package (`aspose-3d-foss`) has not yet been published"; no PyPI badges; the runner never installs the real
  published artifact; the advisory gate would *approve* the stale sentence (it matches
  `_UNPUBLISHED_PACKAGE_SIGNAL_RE`).
- The org-level watcher (`package_publish_watch.py`, daily 10:00 UTC) DID detect it: proposal issues
  #67 (08-29), #70, #72, #74 (09-01) are open and unapplied (`evidence/investigation/watcher-issue-74.json`).
  S-120 does not consult the watcher or its proposals. The system knew; the skill did not.
- The live README on `master` also still says "A PyPI package has not been published yet" (stale since
  08-29). Three upstream README commits landed after our PR #1 (ca442497, d92c9e87, ee05c1ba) — they are
  content to preserve, not to overwrite.
- The candidate on disk (`reports/repo-presenter-regen-full/3d/python/readme.md`) has 3 hard-gate failures
  against today's live README: `dev_test_artifacts_linked` (2), `code_example_api_coverage_survives` (3,
  ST-161), `api_reference_table_completeness` (2).

## 2. Root causes
- **RC-A** Publication state is modeled as static checked-in data with a human-in-the-loop refresh; the
  skill has no live probe, so a README regenerated the day after a publication is wrong by construction.
- **RC-B** The one gate reading the flag was downgraded to advisory to tolerate stale data — a
  data-freshness problem handled as a tiering decision, which also removed the last safety net.
- **RC-C** There is no factpack fact for *what* is published (version, date, artifact kinds, metadata), so
  even a correct flag could not drive precise composition or upstream-issue drafting.
- **RC-D** The runner's install source is a bare boolean; a published artifact that differs from the
  documented tree (version or content) is indistinguishable from a matching one.

## 3. Design (durable, general)
- **D1 probe** `scripts/pipeline/lib/publication_probe.py`: `probe_publication(install_info, *, repo_url,
  fetch=None)` → reuses `package_registries.<type>.check_published` for the identity/boolean; PyPI details
  parsed from the same JSON (latest version, upload time, artifact kinds, requires_python, license,
  project_urls, `repo_url_corroborated`); `effective_published` = live when unambiguous else the record
  (source named); `drift` = live ≠ record; `metadata_findings` (homepage-not-repo, missing-license, no-sdist).
  Never guesses names: manifest-declared `candidate.name` only.
- **D2 single decision point** `_detect_install_info` merges the probe: `published`/`fallback_text_required`
  follow `effective_published`; adds `publication`. Seam `configure(publication_prober=…)`; env
  `README_REFRESH_OFFLINE=1` → record only; in-process memo per (family, platform). `plan` writes it to
  the factpack and `manifest.pinned_inputs.publication` and prints a `PUBLICATION:` line; `approve`
  re-probes and treats a change in `effective_published`/`latest_version` as input drift.
- **D3 gates** `check_installation_matches_live_publication` (HARD; vacuous unless the probe was live and
  unambiguous): published → Installation names the registry-native install command with the real name and
  carries no unpublished-signal phrase; unpublished → no registry install command presented without the
  disclosure. `check_published_version_matches_manifest` (advisory): live latest ≠ manifest version.
- **D4 runner** result gains `environment {install_source, package, version}`; published installs pin
  `name==latest_version`.
- **D5 doc** composition rule "Installation by publication state", badge rule, plan-output contract,
  "registry metadata defects are upstream issues"; mirrors; contract JSON; registry.yaml; module version.
- **D6 registry** S-120 never writes `data/package_registry.json`; the 3d/python flip is applied in this
  session through the watcher's own `apply_proposal` after independent verification (wheel == HEAD), and
  the four proposal issues are closed with that evidence.

## 4. Validation
Scoped suites only (`test_readme_refresh_checks.py`, `test_readme_refresh_run.py`, new
`test_publication_probe.py`, contract parity test); parity gate; `sync_providers --check`;
portfolio audit before/after (accepted delta: 3d/python only). Live proof = TC-REGEN-3D.

## 5. Findings log (append as they happen)
- 2026-09-02 14:05 — investigation complete; see §1.
- 2026-09-02 14:39 — hardening shipped (854e08a5b5): probe reproduces every §1 finding mechanically; portfolio 29/31
  probed live, delta = 3d/python only; drift also on **words/net** (NuGet live, record false).
- 2026-09-02 14:41 — registry flip applied via apply_proposal (f3184918fe); issues #67/#70/#72/#74 closed.
- 2026-09-02 14:42 — TC-REGEN-3D plan: `PUBLICATION: PUBLISHED aspose-3d-foss 26.1.0 on pypi (2026-08-29)`; negative
  control on the stale candidate fails exactly `installation_matches_live_publication` (+3 pre-existing gates).
- 2026-09-02 14:55 — **found live:** `_is_title_case` never implemented its documented internal-capitals clause
  (`glTF` rejected) → fixed 46e9535e28.
- 2026-09-02 15:00 — **found live by running examples on the real wheel:** `Scene.save("x.obj")` raises TypeError
  in ObjExporter (str into binary stream) on 26.1.0 and HEAD; STL/glTF/GLB/3MF fine; no test covers it → upstream-issues.md.
- 2026-09-02 15:05 — **retention finding:** the pre-mission candidate had excluded 5 whole worked examples of the live
  README as "not reproduced" (STL mesh, COLLADA import, parametric primitive, 3MF cube, single-test invocation) →
  all executed on the wheel, restored verbatim; code ledger 12 excluded → 0.
- 2026-09-02 15:15 — final: AWAITING_REVIEW, 0 hard gates, 6/6 self-contained examples clean on PyPI 26.1.0,
  5 user-file placeholders (repo ships no samples), 1 upstream RUNTIME-ERROR (OBJ). Review page evidence/regen/COMPARISON.html.
