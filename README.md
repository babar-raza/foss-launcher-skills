# foss-launcher-skills

The tooling side of the aspose.org monorepo: the pipeline scripts, skills, tests, knowledge
bundles and governance files that used to live in the same repository as the Aspose websites.
The files were extracted with their history from aspose.org at commit
`7b6ee715fb95c112d162804e3d8c6a8e10eb5128` (the base commit). Paths, file contents and
behaviour are unchanged: this is a move, not a rewrite.

## What is here and what is not

- Here: `scripts/`, `skills/`, `.claude/`, `.agents/`, `.kilocode/`, `tests/`, `knowledge/`,
  `docs/` (tooling documents), `schemas/`, `reports/` evidence, root governance files
  (`AGENTS.md`, `CLAUDE.md`, `RUNBOOK.md` and so on), and the sync machinery in
  `scripts/ci/sync_remotes.py` with its two workflow files.
- Not here: the website itself (the pages under `content/`, `themes/`, `layouts/`, `static/`,
  `configs/`, site data and redirects). That stays in aspose.org, which keeps all its files.
  Only the six page templates in `content/templates/` moved.
- Not here either: 20 aspose.org CI workflows, left out on purpose so they do not run on this
  public repository.
- The exact lists are in [`split-manifest/`](split-manifest/MANIFEST.md): `transferred.tsv`,
  `not-transferred.tsv`, `stays.rules.tsv` (what stays, by rule) and `additions.tsv` (files that
  exist only in this repository, such as this README).

## How to run the tools today

The tools still find the repository root from their own file location, so they expect the website
files next to them. Use the overlay layout:

1. Clone aspose.org and check out the base commit (or the commit you work against).
2. Copy the files of this repository over that checkout, same paths, without the `.git` folder.
3. Run the tools from the checkout root, with the interpreter of your choice (shown as
   `<python>` below), for example `<python> -m pytest scripts/pipeline/tests`.

Side-by-side layout (this repository next to a separate aspose.org clone) is not supported yet;
it needs the planned root-path change, which is a separate, later step.

## Branches and sync

- GitHub (`babar-raza/foss-launcher-skills`) is where branches and pull requests live.
- GitLab (`gitlab.recruitize.ai/sialkot/cantt-smallize/foss-launcher-skills`) is a mirror.
  `.github/workflows/sync-to-gitlab.yml` pushes `main` and `split/replica` from GitHub to GitLab,
  fast-forward only, never forced; `.gitlab-ci.yml` carries `main` back to GitHub.
- Credentials are CI secrets and environment variables only; none are stored in this repository.
- Do not force-push or delete the mirrored branches; undo mistakes with a revert commit.

## Regenerate and verify the manifest

The two manifest tools and their tests are in this repository, in `split-manifest/tools/`
(`<python>` is your Python 3 interpreter):

```
<python> split-manifest/tools/build_split_manifest.py --evidence EVIDENCE_DIR --additions split-manifest/additions.tsv --out split-manifest
<python> split-manifest/tools/verify_split_manifest.py --repo . --ref HEAD --manifest-dir split-manifest
<python> -m pytest split-manifest/tools
```

`EVIDENCE_DIR` is the S1 evidence folder of the split plan (hashes.json, report.md and the three
TSV files). The verifier exits 0 when the repository tree is exactly the transferred paths plus the
additions, and every count and hash in `split-manifest/manifest.json` matches the lists.
A merge that moves files must regenerate the manifest; a stale manifest fails the check.
