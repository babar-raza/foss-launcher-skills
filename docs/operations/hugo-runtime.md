# Local Hugo runtime

Agents and developers must use the pinned, checksummed local Hugo under `hugo/runtime/`
instead of whatever `hugo` happens to be on `PATH`, and must never build into the repo.

## Layout

The `hugo/` directory at the repo root is gitignored. Binaries are never committed.

```
hugo/
  README.md
  runtime/
    versions.json                    version, variant, sha256 of hugo.exe, source, verified_at
    0.140.1-standard/                hugo.exe, LICENSE, README.md   (NON-extended)
    0.154.5-extended_withdeploy/     hugo.exe, LICENSE, README.md   (matches CI)
    _downloads/                      release zip + hugo_0.154.5_checksums.txt
```

## Pinned versions

| Version | Variant | Why |
|---------|---------|-----|
| 0.154.5 | extended_withdeploy | Default. CI runs `hugo_extended_withdeploy` 0.154.5; local builds must match it so that local and CI results agree. `hugo deploy` support and extended features (e.g. SCSS) are present. |
| 0.140.1 | standard (non-extended) | Legacy local build kept for comparison and for reproducing older results. It lacks the extended features and `deploy`, so it is not representative of CI. |

## Resolving the binary

```bash
bash scripts/ci/hooks/find_hugo.sh                      # 0.154.5 (default)
bash scripts/ci/hooks/find_hugo.sh --version 0.140.1
HUGO_VERSION=0.140.1 bash scripts/ci/hooks/find_hugo.sh
HUGO="$(bash scripts/ci/hooks/find_hugo.sh)"; "$HUGO" version
```

Version precedence is `--version`, then `HUGO_VERSION`, then `0.154.5`. The script resolves
`hugo/runtime/<version>-*` and requires exactly one match; zero or several matches exit
non-zero with a message. There is deliberately no fallback to `PATH`. It works from any cwd.

## Building without touching the repo

```bash
bash scripts/ci/hooks/hugo_temp_build.sh --config configs/releases.aspose.org.toml \
    [--version V] [--source-dir DIR] [--exec 'ls "$HUGO_OUT" | head']
```

- Creates `${TMPDIR:-/tmp}/aspose-hugo.XXXXXX` and builds into `<tmp>/out`
  (`hugo --config <config> --source <source-dir> -d <tmp>/out --quiet`).
- `--source-dir` defaults to the repo root. Hugo may still write the gitignored
  `.hugo_build.lock` and `resources/` in the source dir; the build output never lands there.
- `--exec` runs a shell command with `HUGO_OUT=<tmp>/out` so you can inspect output
  (grep, find, compare) before it is deleted.
- The temp dir is removed on normal exit, build failure, `--exec` failure, SIGINT and SIGTERM.
- Sibling `aspose-hugo.*` dirs older than 24 hours (left by killed runs, e.g. SIGKILL) are swept
  at the start of every run.
- Exit code is hugo's on build failure, otherwise the `--exec` command's (130/143 on INT/TERM).

## Rule

Never build into the repo, `public/`, or any other persistent directory. Use
`hugo_temp_build.sh`. Do not copy Hugo binaries into tracked paths.

## Re-provisioning

Needed on a new machine or after deleting `hugo/`. All steps from the repo root in Git Bash.

0.154.5 extended_withdeploy (download and verify; stop on any mismatch):

```bash
mkdir -p hugo/runtime/_downloads hugo/runtime/0.154.5-extended_withdeploy
cd hugo/runtime/_downloads
B=https://github.com/gohugoio/hugo/releases/download/v0.154.5
Z=hugo_extended_withdeploy_0.154.5_windows-amd64.zip
curl -fL -o "$Z" "$B/$Z"
curl -fL -o hugo_0.154.5_checksums.txt "$B/hugo_0.154.5_checksums.txt"
exp="$(grep " $Z\$" hugo_0.154.5_checksums.txt | awk '{print $1}')"
act="$(sha256sum "$Z" | awk '{print $1}')"
[ -n "$exp" ] && [ "$exp" = "$act" ] || { echo "CHECKSUM MISMATCH: expected=$exp actual=$act" >&2; exit 1; }
cd ../0.154.5-extended_withdeploy && unzip -o "../_downloads/$Z" hugo.exe LICENSE README.md
./hugo.exe version     # must show +extended+withdeploy
```

0.140.1 standard: download `hugo_0.140.1_windows-amd64.zip` and `hugo_0.140.1_checksums.txt` from
`https://github.com/gohugoio/hugo/releases/tag/v0.140.1`, verify the zip the same way, and
extract `hugo.exe`, `LICENSE`, `README.md` into `hugo/runtime/0.140.1-standard/`.

Afterwards update `hugo/runtime/versions.json` (sha256 of the new `hugo.exe`, source, date) and
confirm with `bash scripts/ci/hooks/find_hugo.sh --version <V>`.

To add a new version, create `hugo/runtime/<V>-<variant>/` the same way. Keep exactly one directory
per version number so resolution stays unambiguous.
