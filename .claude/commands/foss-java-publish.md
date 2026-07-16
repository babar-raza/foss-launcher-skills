<!-- CONTRACT: agent-executed
     purpose: publish a FOSS Java library to Maven Central with surgical pom changes,
              GHA automation via tag-push trigger, PUBLISHING.md documentation committed
              to the product repo, and aspose.org English content healing
     preconditions: active session; FOSS repo accessible on GitHub; GPG backup key at
                    $USERPROFILE\OneDrive\Documents\aspose-foss-gpg-signing-key.asc;
                    sonatype_user + sonatype_password in process env;
                    GPG_PASSPHRASE in Windows User-scope env
     postcondition: artifact live on Maven Central; PUBLISHING.md committed to product repo;
                    aspose.org English content files healed and committed; all changes pushed
     idempotent: Phase A skipped if version already on Maven Central; Phase B (content
                 healing) always runs regardless
     verified: 2026-07-16
-->
# S-110: FOSS Java Publish — Maven Central Publication and Content Healing

**Arguments**: $ARGUMENTS
Expected format:
```
{github-org}/{repo-name} {artifact-id} {version} [--java {java-version}] [--family {content-family}]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `{github-org}/{repo-name}` | Yes | Full GitHub slug, e.g. `aspose-3d-foss/Aspose.3D-FOSS-for-Java` |
| `{artifact-id}` | Yes | Maven artifactId, e.g. `aspose-3d-foss` or `aspose-pdf-foss` — immutable after publish |
| `{version}` | Yes | Release version, e.g. `26.5.0` — must not contain SNAPSHOT or alpha |
| `--java` | No | Java version for GHA temurin runner (default: `17`); MUST match pom.xml `<maven.compiler.source>` |
| `--family` | No | Content family slug for aspose.org healing, e.g. `3d`, `pdf` (derived from repo name if omitted) |

**Examples:**
```
# Publish Aspose.3D FOSS for Java (Java 21 target matches pom)
/foss-java-publish aspose-3d-foss/Aspose.3D-FOSS-for-Java aspose-3d-foss 26.7.0 --java 21

# Publish Aspose.PDF FOSS for Java (Java 11 target matches pom)
/foss-java-publish aspose-pdf-foss/Aspose.PDF-FOSS-for-Java aspose-pdf-foss 26.8.0 --java 11

# Re-run content healing only (Phase A already complete — artifact exists on Central)
/foss-java-publish aspose-3d-foss/Aspose.3D-FOSS-for-Java aspose-3d-foss 26.7.0 --java 21
# Skill detects version on Maven Central, skips Phase A, runs Phase B directly.
```

---

## Purpose

Publish a FOSS Java library to Maven Central with exactly the surgical changes required —
no source code modifications, no README rewrites, no test additions. Documents every
change in a `PUBLISHING.md` file committed to the product repo, so the product team
inherits a fully self-contained runbook. Heals all English aspose.org content pages to
reflect the new Maven coordinates.

**Use S-110 when:**
- A FOSS Java repo needs its first Maven Central publication
- A subsequent version is ready to publish (re-run skips Phase A, heals new content)
- Content pages need coordinate healing after a manual publication

**Do NOT use S-110 for:**
- Non-Java repos (Python, .NET, C++ — different publication paths)
- Repos already on Maven Central at the correct coordinates (Phase A auto-skips; verify Phase B is still needed)
- Content-only coordinate healing without a real artifact publication (use S-73 batch instead)

---

## Pre-conditions

1. Active session ledger (`session_ledger.py current` exits 0)
2. `sonatype_user` and `sonatype_password` are set in the process environment
3. `GPG_PASSPHRASE` is set in Windows User-scope environment
4. GPG backup key exists at `$env:USERPROFILE\OneDrive\Documents\aspose-foss-gpg-signing-key.asc` OR key `E176D5CBCA1DCC62` is already in local keyring
5. `gh auth status` passes — gh CLI is authenticated
6. `templates/workflows/maven-central-release.yml.tpl` exists in aspose.org repo
7. Target FOSS repo exists on GitHub and agent has push access

---

## Steps

> **Skill context gate** — run before step A1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-110 --scope "*"
> ```

---

## Phase A: FOSS Repo Publication

### Step A1 — Pre-flight idempotency check

Before cloning or editing anything, check if the artifact already exists on Maven Central:

```bash
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "https://repo1.maven.org/maven2/org/aspose/{artifact-id}/{version}/")
```

- HTTP 200 → Version already published. Print: `Phase A skipped — org.aspose:{artifact-id}:{version} already on Maven Central`. Proceed directly to Step B1.
- HTTP 404 → Not yet published. Continue with Step A2.

This check is the FIRST action. Do not clone or edit any file without running it.

### Step A2 — Pre-flight credential validation

Read and validate all required credentials. Block on any failure with a specific message.

```powershell
$SONATYPE_U = $env:sonatype_user
$SONATYPE_P = $env:sonatype_password
$GPG_PP     = [System.Environment]::GetEnvironmentVariable('GPG_PASSPHRASE', 'User')

if (-not $SONATYPE_U) { throw "sonatype_user not found in process env." }
if (-not $SONATYPE_P) { throw "sonatype_password not found in process env." }
if (-not $GPG_PP)     { throw "GPG_PASSPHRASE not found in Windows User scope." }

# Verify GPG key in local keyring; import from backup if absent
$keycheck = & gpg --list-secret-keys --keyid-format LONG E176D5CBCA1DCC62 2>&1
if ($LASTEXITCODE -ne 0) {
    $backup = "$env:USERPROFILE\OneDrive\Documents\aspose-foss-gpg-signing-key.asc"
    if (-not (Test-Path $backup)) {
        throw "GPG key E176D5CBCA1DCC62 not in keyring and backup not found at: $backup"
    }
    & gpg --import $backup
    if ($LASTEXITCODE -ne 0) { throw "GPG import from backup failed." }
}

# Verify gh CLI
& gh auth status 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "gh CLI not authenticated." }

Write-Host "Pre-flight PASSED: sonatype_user=$($SONATYPE_U.Substring(0,3))*** GPG key present"
```

### Step A3 — Clone FOSS repo

```bash
git clone https://github.com/{org}/{repo}.git "D:/OneDrive/Documents/GitHub/{repo-name}/"
```

Use `-C {repo-path}` for all subsequent git operations. Do NOT rely on `cd` persisting between tool calls.

### Step A4 — Java version pre-check (HALT before any edits)

Read `pom.xml` and extract `<maven.compiler.source>`. Compare to `--java` arg (default `17`).

```bash
POM_JAVA=$(python -c "import xml.etree.ElementTree as ET; t=ET.parse('{path}/pom.xml'); \
  ns={'m':'http://maven.apache.org/POM/4.0.0'}; \
  print(t.find('m:properties/m:maven.compiler.source', ns).text)")
echo "pom compiler source: $POM_JAVA, --java arg: {java-arg}"
```

If they differ: **HALT** with:
```
Java version mismatch: pom.xml <maven.compiler.source> is {pom-ver} but --java arg is {arg-ver}.
Pass --java {pom-ver} to match the pom, OR update pom.xml to target Java {arg-ver}.
No files have been modified.
```

### Step A5 — Surgical pom.xml audit

Read the current `pom.xml`. For each required element, record current state and whether it needs to be added or corrected. Print this table before making any changes.

**Required elements:**

| Element | Required value | Action if missing/wrong |
|---------|---------------|------------------------|
| `<groupId>` | `org.aspose` | Correct — IMMUTABLE after first publish |
| `<artifactId>` | `{artifact-id}` arg | Correct — IMMUTABLE after first publish |
| `<version>` | `{version}` arg | Correct |
| `<url>` | `https://github.com/{org}/{repo}` | Add |
| `<licenses><license>` | MIT block | Add |
| `<developers><developer>` | Canonical block (see below) | Add or replace non-canonical form |
| `<scm>` | GitHub scm block | Add |
| maven-source-plugin 3.4.0 | `jar-no-fork` goal in `attach-sources` | Add |
| maven-javadoc-plugin 3.12.0 | `failOnError=false`; `outputDirectory=${project.build.directory}/apidocs` | Add |
| maven-gpg-plugin 3.2.8 | keyname `E176D5CBCA1DCC62`; `passphraseEnvName=GPG_PASSPHRASE` | Add |
| central-publishing-maven-plugin 0.11.0 | `autoPublish=true`; `waitUntil=validated`; `publishingServerId=central` | Add |

**Note on `waitUntil`**: The correct parameter is `waitUntil` (camelCase). The misspelling `waitUtil` was present in the 2026-07-16 sprint artifacts — do NOT repeat it. The plugin silently ignores unknown parameters; `waitUtil` fell back to default (no waiting), masking portal validation failures.

**Canonical developer block** (enforce across all org.aspose publications):
```xml
<developers>
  <developer>
    <name>Aspose</name>
    <organization>Aspose Pty Ltd</organization>
    <organizationUrl>https://www.aspose.com/</organizationUrl>
  </developer>
</developers>
```

If `<groupId>` or `<artifactId>` is already published on Maven Central at a DIFFERENT value than the arguments, **HALT** — these are immutable once any version is published.

**Required plugin XML blocks (copy verbatim, fill in values):**

```xml
<!-- maven-source-plugin: generates -sources.jar required by Maven Central -->
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-source-plugin</artifactId>
  <version>3.4.0</version>
  <executions>
    <execution>
      <id>attach-sources</id>
      <goals><goal>jar-no-fork</goal></goals>
    </execution>
  </executions>
</plugin>

<!-- maven-javadoc-plugin: generates -javadoc.jar required by Maven Central -->
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-javadoc-plugin</artifactId>
  <version>3.12.0</version>
  <configuration>
    <failOnError>false</failOnError>
    <outputDirectory>${project.build.directory}/apidocs</outputDirectory>
  </configuration>
  <executions>
    <execution>
      <id>attach-javadocs</id>
      <goals><goal>jar</goal></goals>
    </execution>
  </executions>
</plugin>

<!-- maven-gpg-plugin: signs all artifacts with key E176D5CBCA1DCC62 -->
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-gpg-plugin</artifactId>
  <version>3.2.8</version>
  <configuration>
    <keyname>E176D5CBCA1DCC62</keyname>
    <passphraseEnvName>GPG_PASSPHRASE</passphraseEnvName>
  </configuration>
  <executions>
    <execution>
      <id>sign-artifacts</id>
      <phase>verify</phase>
      <goals><goal>sign</goal></goals>
    </execution>
  </executions>
</plugin>

<!-- central-publishing-maven-plugin: uploads to Sonatype Central Portal -->
<!-- CRITICAL: parameter is waitUntil (NOT waitUtil — plugin silently ignores unknown keys) -->
<plugin>
  <groupId>org.sonatype.central</groupId>
  <artifactId>central-publishing-maven-plugin</artifactId>
  <version>0.11.0</version>
  <extensions>true</extensions>
  <configuration>
    <publishingServerId>central</publishingServerId>
    <autoPublish>true</autoPublish>
    <waitUntil>validated</waitUntil>
  </configuration>
</plugin>
```

### Step A6 — Apply pom.xml patches (minimum required)

Apply ONLY the changes identified in Step A5. Do not reformat, do not reorder existing elements, do not touch anything not in the audit table.

**BOM-zero enforcement** — all file writes from PowerShell MUST use:
```powershell
[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
```

PowerShell `Set-Content -Encoding UTF8` adds a UTF-8 BOM that breaks `javac` on Linux runners. This was the root cause of the post-hoc `85948b4` fix commit in the 3D repo during the 2026-07-16 sprint.

After writing, verify no BOM:
```powershell
$b = [System.IO.File]::ReadAllBytes($path)
if ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
    throw "BOM detected in $path — write failed, aborting"
}
```

Verify `waitUntil` spelling in the written pom:
```bash
grep "waitUntil" {path}/pom.xml  || { echo "ERROR: waitUntil missing from pom.xml"; exit 1; }
grep "waitUtil"  {path}/pom.xml  && { echo "ERROR: waitUtil typo found — must be waitUntil"; exit 1; } || true
```

### Step A7 — .gitignore

If `.gitignore` exists: append any missing lines from: `target/`, `*.asc`, `.secrets`, `.env.act`.
If `.gitignore` is absent: create with all four lines.

BOM-zero enforcement applies.

Verify `target/` is now in `.gitignore` before proceeding.

### Step A8 — Create GHA workflow from template

Read `templates/workflows/maven-central-release.yml.tpl` from the aspose.org repo.
Substitute ALL occurrences of `{ARTIFACT_ID}` with `{artifact-id}` and `{JAVA_VERSION}` with `{java-ver}`.
Write to `.github/workflows/maven-central-release.yml` in the FOSS repo. BOM-zero enforcement.

Do NOT touch any existing workflow files (e.g. `build.yml`).

Verification:
```bash
# At least 8 occurrences of artifact-id (guards, jar checks, Maven Central URL)
grep -c "{artifact-id}" {path}/.github/workflows/maven-central-release.yml

# Zero placeholder tokens remaining
grep "{ARTIFACT_ID}" {path}/.github/workflows/maven-central-release.yml && exit 1 || true
grep "{JAVA_VERSION}" {path}/.github/workflows/maven-central-release.yml && exit 1 || true

# waitUntil spelling correct
grep "waitUntil" {path}/.github/workflows/maven-central-release.yml
grep "waitUtil"  {path}/.github/workflows/maven-central-release.yml && exit 1 || true
```

### Step A9 — Write PUBLISHING.md to product repo

Write `PUBLISHING.md` to the root of the FOSS repo using the template below, filled with
actual sprint values. This file IS committed to the product repo — it is the product team's
runbook after the agent session ends. BOM-zero enforcement.

**PUBLISHING.md template (fill all `{placeholders}` at runtime):**

```markdown
# Maven Central Publishing — {repo-name}

> **Maintained by CI** — do not edit manually. Generated by aspose.org S-110 foss-java-publish skill.

## What Was Changed and Why

Surgical changes only — source code, README, existing workflows, and tests were NOT modified.

### pom.xml changes

| Element | Before | After | Required by |
|---------|--------|-------|-------------|
| groupId | {old-groupId} | org.aspose | Maven Central namespace enforcement |
| artifactId | {old-artifactId} | {artifact-id} | Correct identifier (immutable after first publish) |
| version | {old-version} | {version} | Release version (no SNAPSHOT/alpha) |
| url | {was present or: absent} | {repo-url} | Maven Central metadata requirement |
| licenses | {was present or: absent} | MIT License block | Maven Central metadata requirement |
| developers | {was present or: absent/non-canonical} | Canonical Aspose Pty Ltd block | Maven Central metadata requirement |
| scm | {was present or: absent} | GitHub scm block | Maven Central metadata requirement |
| maven-source-plugin 3.4.0 | absent | added | Maven Central requires -sources.jar |
| maven-javadoc-plugin 3.12.0 | absent | added (failOnError=false) | Maven Central requires -javadoc.jar |
| maven-gpg-plugin 3.2.8 | absent | added (key E176D5CBCA1DCC62) | Maven Central requires signed artifacts |
| central-publishing-maven-plugin 0.11.0 | absent | added (autoPublish=true, waitUntil=validated) | Upload to Central Portal |

### Files added by this skill

| File | Purpose |
|------|---------|
| `.github/workflows/maven-central-release.yml` | CI pipeline: tag push → build → sign → publish |
| `.gitignore` | Excludes `target/`, `*.asc` from commits |
| `PUBLISHING.md` | This file — release runbook |

### Files NOT changed

Source code, README, existing workflows, tests, docs, and all files not listed above.

## What Needs Further Work (Product Team Actions)

| Priority | Item | File | What to do |
|----------|------|------|-----------|
| **High** | Update README Maven badge | README.md | Badge URL still points to old artifactId/groupId |
| **High** | Update README `<dependency>` snippet | README.md | Must show `org.aspose:{artifact-id}:{version}` |
| **High** | Document version alignment policy | README.md | State which commercial version this FOSS version corresponds to |
| Medium | Add CHANGELOG.md | repo root | Maven Central users expect per-version changelogs |
| Medium | Java {pom-java-ver} target review | pom.xml | Consider LTS (11 or 17) for broader compatibility |
| Medium | Complete `<developer>` block | pom.xml | Add `<id>` and `<email>` fields |
| Medium | Add LICENSE file | repo root | GitHub and Maven Central badge systems expect standalone file |
| Low | Add `<scm><tag>v{version}</tag>` | pom.xml | Enables `mvn release:*` plugin |
| Low | Bump `central-publishing-maven-plugin` if needed | pom.xml | Note: `waitUtil` (wrong) → `waitUntil` (correct) in versions < 0.11.1 |

## Smoke Test Results

| Test | Result |
|------|--------|
| Local build (gpg.skip=true) | {PASS or FAIL: detail} |
| Ubuntu dry-run (workflow_dispatch) | {PASS or FAIL: detail} |
| Artifact on Maven Central (HTTP 200) | {PASS: URL confirmed} |
| JAR smoke compile | {PASS or FAIL: detail} |
| C7 findings (missing classes) | {N missing classes, or: none} |

## How to Cut Future Releases

Publishing a new version requires **one command**:

```bash
# 1. Bump version in pom.xml, commit, push
sed -i 's/<version>{version}<\/version>/<version>NEW_VERSION<\/version>/' pom.xml
git commit -am "chore: bump version to NEW_VERSION"
git push origin {default-branch}

# 2. Push a tag — GitHub Actions does the rest
git tag vNEW_VERSION
git push origin vNEW_VERSION
```

GitHub Actions (`maven-central-release.yml`) will automatically:
1. Create a GitHub Release with auto-generated release notes
2. Build with Java {java-ver}; generate `-sources.jar` and `-javadoc.jar`
3. Sign all 3 jars with GPG key E176D5CBCA1DCC62
4. Upload to Sonatype Central Portal and publish (`autoPublish=true`)
5. Artifact available at: `https://repo1.maven.org/maven2/org/aspose/{artifact-id}/`

## GitHub Secrets (do not remove)

| Secret | Purpose |
|--------|---------|
| `GPG_PRIVATE_KEY` | GPG signing key (armored RSA 4096, expires 2028-06-04) |
| `GPG_PASSPHRASE` | GPG key passphrase |
| `MAVEN_CENTRAL_USERNAME` | Sonatype Central Portal username |
| `MAVEN_CENTRAL_PASSWORD` | Sonatype Central Portal token |

For secret rotation or recovery: contact the infrastructure team.

## Publication History

| Version | Date | Published by | Maven Central |
|---------|------|-------------|---------------|
| {version} | {date} | S-110 foss-java-publish (automated) | https://repo1.maven.org/maven2/org/aspose/{artifact-id}/{version}/ |
```

### Step A10 — Surgical boundary verification

Assert that the diff is limited to exactly the allowed files:

```bash
git -C {path} diff --name-only HEAD
git -C {path} ls-files --others --exclude-standard
```

Allowed files (new or modified): `pom.xml`, `.gitignore`, `.github/workflows/maven-central-release.yml`, `PUBLISHING.md`.

If ANY other file appears: **HALT** — "Surgical boundary violated: unexpected file `{name}` in diff. Review and unstage before proceeding. No commit was made."

### Step A11 — Local build verification

```bash
mvn -f {path}/pom.xml clean package -Dgpg.skip=true -DskipTests 2>&1
```

Must print `BUILD SUCCESS`. If it fails: diagnose the Maven error output, fix in pom.xml (never fix source code unless the compile error is a direct consequence of pom changes), re-run. Do NOT push until local build passes.

Verify all 3 jars:
```bash
ls {path}/target/{artifact-id}-{version}.jar          # main jar
ls {path}/target/{artifact-id}-{version}-sources.jar  # sources jar
ls {path}/target/{artifact-id}-{version}-javadoc.jar  # javadoc jar
```

Record BUILD SUCCESS as the smoke test result for PUBLISHING.md.

### Step A12 — Set GitHub Secrets (4 secrets, non-interactive)

**GPG private key — read from backup file, NOT from live export.**

Live export (`gpg --armor --export-secret-keys`) opens a pinentry GUI dialog that hangs
indefinitely in non-TTY agent sessions. This was confirmed in the 2026-07-16 sprint.
Always use the backup `.asc` file:

```powershell
$keyContent = [System.IO.File]::ReadAllText(
    "$env:USERPROFILE\OneDrive\Documents\aspose-foss-gpg-signing-key.asc")
$keyContent | gh secret set GPG_PRIVATE_KEY --repo {org}/{repo}
```

Remaining 3 secrets via `--body` (non-interactive):
```powershell
gh secret set GPG_PASSPHRASE         --body $GPG_PP      --repo {org}/{repo}
gh secret set MAVEN_CENTRAL_USERNAME --body $SONATYPE_U  --repo {org}/{repo}
gh secret set MAVEN_CENTRAL_PASSWORD --body $SONATYPE_P  --repo {org}/{repo}
```

Verify: `gh secret list --repo {org}/{repo}` → exactly 4 rows.

### Step A13 — Commit and push to FOSS repo

Stage ONLY the four allowed files:
```bash
git -C {path} add pom.xml .gitignore \
    .github/workflows/maven-central-release.yml PUBLISHING.md
```

Verify staged file list matches the boundary before committing:
```bash
git -C {path} diff --staged --name-only
# Must show only: pom.xml  .gitignore  .github/workflows/maven-central-release.yml  PUBLISHING.md
```

Commit with structured message:
```
ci: add Maven Central publishing pipeline (S-110)

Surgical changes only — source code and README not modified.

pom.xml:
  - groupId: {old} → org.aspose  [if changed]
  - artifactId: {old} → {artifact-id}  [if changed]
  - version: {old} → {version}
  - Added: url, licenses, developers (canonical Aspose Pty Ltd), scm
  - Added plugins: maven-source-plugin 3.4.0, maven-javadoc-plugin 3.12.0,
                   maven-gpg-plugin 3.2.8,
                   central-publishing-maven-plugin 0.11.0 (waitUntil=validated)
Added: .github/workflows/maven-central-release.yml (tag-push trigger)
Added: .gitignore  [if created]
Added: PUBLISHING.md (release runbook for product team)
```

**Push using GH_TOKEN URL** — GCM credential dialogs block non-TTY sessions:
```bash
git -C {path} push \
  "https://x-access-token:${GH_TOKEN}@github.com/{org}/{repo}.git" {branch}
```

### Step A14 — Ubuntu dry-run

```bash
gh workflow run maven-central-release.yml --repo {org}/{repo} -f target=ubuntu
sleep 10
RUN_ID=$(gh run list --repo {org}/{repo} --workflow maven-central-release.yml \
         --limit 1 --json databaseId -q '.[0].databaseId')
```

Poll every 30s, timeout 20 min:
```bash
gh run view $RUN_ID --repo {org}/{repo} --json status,conclusion \
  -q '"[\(.status)] \(.conclusion // "pending")"'
```

On `completed/success`: confirm log contains "DEPLOY SKIPPED".
On failure: `gh run view $RUN_ID --repo {org}/{repo} --log-failed` → halt with output.

### Step A15 — Tag push → release deploy

```bash
git -C {path} tag v{version}
git -C {path} push \
  "https://x-access-token:${GH_TOKEN}@github.com/{org}/{repo}.git" v{version}
```

Poll release-deploy run every 30s, timeout 30 min. On success verify GitHub Release:
```bash
gh release view v{version} --repo {org}/{repo}
```

### Step A16 — Maven Central confirmation

Poll availability of all three key artifacts every 5 min, up to 4h:
```bash
for SUFFIX in ".jar" ".pom" "-sources.jar"; do
  URL="https://repo1.maven.org/maven2/org/aspose/{artifact-id}/{version}/{artifact-id}-{version}${SUFFIX}"
  # poll until HTTP 200
done
```

All three must return HTTP 200 before confirming success.

Final Maven resolution check:
```bash
mvn dependency:get -Dartifact=org.aspose:{artifact-id}:{version} -q
# Must print: BUILD SUCCESS
```

Record confirmation URL in PUBLISHING.md Publication History table.

---

## Phase B: Artifact Verification and Content Healing

### Step B1 — Download and inspect published JAR

```bash
mvn dependency:get -Dartifact=org.aspose:{artifact-id}:{version}:jar -q
JAR=$(find ~/.m2/repository/org/aspose/{artifact-id}/{version} \
      -name "{artifact-id}-{version}.jar" | head -1)
jar tf "$JAR" | grep '\.class$' | sed 's|/|.|g; s|\.class$||' \
  > /tmp/{artifact-id}-classes.txt
wc -l /tmp/{artifact-id}-classes.txt
```

Print: total class count and top-level packages (first 3 dotted segments of each unique prefix).

### Step B2 — Compile smoke test against live artifact

Identify the most fundamental public class in the library from `/tmp/{artifact-id}-classes.txt`
(e.g. `com.aspose.threed.Scene` for 3D, `com.aspose.pdf.Document` for PDF). Generate a
minimal Java test file and compile against the live JAR:

```java
// SmokeTest.java — generated, compiled, and discarded
import com.aspose.{pkg}.{KeyClass};
public class SmokeTest {
    public static void main(String[] args) {
        System.out.println("{KeyClass} loaded: " + {KeyClass}.class.getName());
    }
}
```

```bash
javac -cp "$JAR" /tmp/SmokeTest.java -d /tmp/
java  -cp "$JAR:/tmp" SmokeTest
```

Record result as PASS or FAIL (with error) in PUBLISHING.md. A FAIL does not block the
skill — it is a finding for the product team (packaging problem, API incompatibility, etc.).

### Step B3 — Cross-check content code snippets against JAR

Grep all English Java content files for `import com.aspose.*` statements in code blocks.
For each unique import, verify class presence in `/tmp/{artifact-id}-classes.txt`.

```bash
grep -r "import com\.aspose\." content/*/en/{family}/java/ \
     content/blog.aspose.org/{family}/java/ 2>/dev/null | \
  grep -oP 'import (com\.aspose\.[A-Za-z0-9.]+)' | sort -u
```

For each class: `grep -F "com.aspose.{pkg}.{Class}" /tmp/{artifact-id}-classes.txt`

Record C7 findings (imports referencing absent classes). These are NOT edited — they go
into PUBLISHING.md for the product team.

### Step B4 — Content healing pre-edit audit

Grep all English-scope content files for the five coordinate check patterns:

| Check | Grep pattern | Expected fix |
|-------|-------------|-------------|
| C1 | Wrong `<groupId>` in dependency block for this artifact | → `org.aspose` |
| C2 | Wrong `<artifactId>` in dependency block | → `{artifact-id}` |
| C3 | Stale `<version>` in dependency block | → `{version}` |
| C4 | Wrong Gradle `implementation '...'` coordinate | Fix groupId/artifactId/version |
| C6 | Stale `model_version:` in frontmatter | → `{version}` (no `^` anchor — some files have indented `  model_version:`) |

**English scope** (no locale-suffix files):
- `content/blog.aspose.org/{family}/java/**/*.md`
- `content/docs.aspose.org/en/{family}/java/**/*.md`
- `content/kb.aspose.org/en/{family}/java/**/*.md`

Do NOT edit: `content/reference.aspose.org/` (auto-generated), any file with a locale
suffix (e.g. `index.fr.md`, `index.de.md`).

Print the full pre-edit table to the operator before ANY edits:

```
=== CONTENT HEALING PLAN (operator confirmation required) ===

Artifact: org.aspose:{artifact-id}:{version}
Scope:    English-only .md files (no locale suffix)

C1 (groupId fix):    N files
C2 (artifactId fix): N files
C3 (version fix):    N files
C4 (gradle fix):     N files
C6 (model_version):  N files

Sample substitutions:
  content/docs.aspose.org/en/{family}/java/foo.md
    <groupId>com.aspose</groupId>  →  <groupId>org.aspose</groupId>
    model_version: 26.1.0          →  model_version: {version}
  ...

C7 findings (NOT edited — reported to product team):
  import com.aspose.{family}.{MissingClass} — class absent from published JAR
  ...

Proceed with healing? [Y/N]
```

Wait for operator confirmation before making any file edits.
If `--auto` flag was passed in $ARGUMENTS, proceed without the prompt.

### Step B5 — Apply content healing

For each file in the approved plan, use Read → Edit to apply the substitutions.
After editing each file, verify it no longer matches the stale pattern.

C6 pattern note: search with `model_version: {old-value}` (no `^` anchor) to catch
both `model_version:` at column 0 and `  model_version:` (indented form). The `^` anchor
misses indented frontmatter — this caused missed files in the 2026-07-16 PDF sprint.

### Step B6 — Post-healing verification sweep

After all edits, re-run ALL five grep patterns across the full scope. Every sweep must
return zero matches. Do not proceed to commit until all five are clean.

```bash
# C1: zero wrong groupIds in dependency blocks
# C2: zero stale artifactIds in dependency blocks
# C3: zero stale versions in dependency blocks
# C4: zero wrong gradle coordinates
# C6: zero stale model_version values (check both column-0 and indented form)
```

If any match remains: fix and re-run the sweep. Do not bypass this gate.

### Step B7 — Skill run record management

Before committing to aspose.org:

**Drain stale pending records.** Stale records from prior sessions cause the pre-commit
hook to fail with "Declared skills do not match skill run record":

```bash
python scripts/pipeline/commands/ops/skill_run_manager.py find-pending
# For each stale record found:
python scripts/pipeline/commands/ops/skill_run_manager.py finalize \
  --record-id {id} --outcome success
```

**Create a fresh non-retroactive record.** Records created with `--retroactive` are
excluded from `find-pending` by the script code (`if "retroactive" not in f.name`).
Create WITHOUT `--retroactive`:

```bash
python scripts/pipeline/commands/ops/skill_run_manager.py create \
  --skills S-73 S-76 S-110 --run-type targeted
```

### Step B8 — Commit healed content via S-76

**Evidence churn bypass.** The pre-commit hook runs `check_evidence_churn.py --mode staged`
which blocks commits where ≥20 files have evidence-only frontmatter changes. The hook
reads the bypass annotation from `$EVIDENCE_RESTAMP_MSG` env var — NOT from the commit
message. Git writes `COMMIT_EDITMSG` AFTER the pre-commit hook exits, so embedding the
annotation in the commit message has zero effect.

```bash
EVIDENCE_RESTAMP_MSG="EVIDENCE-RESTAMP: approved by {operator} on {date}, \
reason: bulk Maven coordinate healing for org.aspose:{artifact-id}:{version}" \
git commit -m "content({family}/java): fix Maven coordinates for org.aspose:{artifact-id}:{version}

- C1: groupId corrected to org.aspose in all dependency blocks
- C2: artifactId corrected to {artifact-id} in all dependency blocks
- C3: version updated to {version} in all dependency blocks
- C4: Gradle coordinates corrected
- C6: model_version updated to {version} in frontmatter
Files: N English source files across blog/docs/kb
Artifact: org.aspose:{artifact-id}:{version} (live on Maven Central)
Skills invoked: [S-73, S-76, S-110]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**Pre-commit hook sync.** `.git/hooks/pre-commit` is a COPY (not a symlink) of
`scripts/pre-commit-audit.sh`. If the source was patched since the last copy:
```bash
cp scripts/pre-commit-audit.sh .git/hooks/pre-commit
```

**Staged file boundary check.** Before committing, verify no reference or locale files
were accidentally staged:
```bash
git diff --staged --name-only | grep "reference.aspose.org" && \
  { echo "ERROR: reference files staged — unstage them"; exit 1; } || true
git diff --staged --name-only | grep -E '\.[a-z]{2}\.md$' && \
  { echo "ERROR: locale files staged — unstage them"; exit 1; } || true
```

### Step B9 — Push aspose.org

```bash
git push "https://x-access-token:${GH_TOKEN}@github.com/Aspose/aspose.org.git" main
```

### Step B10 — Final summary

Print a complete summary of all actions taken:

```
=== foss-java-publish S-110 COMPLETE ===

Artifact:        org.aspose:{artifact-id}:{version}
Maven Central:   https://repo1.maven.org/maven2/org/aspose/{artifact-id}/{version}/
                 (HTTP 200 confirmed — jar + pom + sources)
GitHub Release:  https://github.com/{org}/{repo}/releases/tag/v{version}
PUBLISHING.md:   committed to {org}/{repo} (product team runbook)

Smoke test:      {PASS | FAIL: {error}}
JAR classes:     N classes ({top-level-packages})
C7 findings:     N missing classes (see PUBLISHING.md for details)

aspose.org commit: {sha}
  C1: N files  C2: N files  C3: N files  C4: N files  C6: N files
  Total healed: N English files (blog/docs/kb)
  Post-sweep:   zero stale patterns confirmed
```

---

> **Skill context close** — run after Step B10:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-110 --status completed
> ```

---

## Post-conditions

**If COMPLETE (both phases):**
- `org.aspose:{artifact-id}:{version}` is live on Maven Central (HTTP 200 for jar + pom + sources)
- GitHub Release `v{version}` exists in the product repo
- `PUBLISHING.md` is committed to the product repo root
- `pom.xml`, `.gitignore`, `maven-central-release.yml` are the only changed files in the product repo
- All aspose.org English content files for `{family}/java` have correct coordinates
- Post-healing grep sweep returns zero matches on all five patterns
- aspose.org commit pushed to main

**If Phase A skipped (version already on Central):**
- All Phase B postconditions apply

**If Phase B operator declined:**
- Maven Central publication is complete; content healing was not performed

---

## Refusal and halt conditions

| Condition | Response |
|-----------|----------|
| `sonatype_user` or `sonatype_password` absent from env | HALT — specific missing var named |
| `GPG_PASSPHRASE` absent from Windows User scope | HALT |
| GPG key absent from keyring AND backup file missing | HALT with backup path |
| `gh auth status` fails | HALT |
| `templates/workflows/maven-central-release.yml.tpl` missing | HALT — cannot generate workflow |
| `--java` arg does not match `<maven.compiler.source>` in pom | HALT before any file edits |
| `<groupId>` or `<artifactId>` already on Central at different coordinates | HALT — immutable |
| BOM detected in written pom.xml | HALT — abort and diagnose write tool |
| `waitUtil` typo found in written files | HALT — fix before staging |
| Surgical boundary violated (unexpected file in diff) | HALT before staging |
| Local build fails | Diagnose and fix; do not push until `BUILD SUCCESS` |
| Dry-run workflow fails | HALT — print `--log-failed` output |
| Content healing operator declines | Halt Phase B; Phase A result stands |
| Reference or locale files staged | HALT — unstage before committing |

### What S-110 will never do

- Modify source code, test files, README, or existing workflow files in the product repo
- Push more than four files to the FOSS repo: `pom.xml`, `.gitignore`, `maven-central-release.yml`, `PUBLISHING.md`
- Use live `gpg --export-secret-keys` (opens pinentry GUI, blocks non-TTY sessions)
- Skip the surgical boundary check before staging
- Skip the post-healing grep sweep before committing
- Commit to aspose.org without draining stale skill run records first
- Edit locale-suffix files or `reference.aspose.org` content

---

## Error handling

| Error | Action |
|-------|--------|
| Maven Central HTTP 5xx | Wait 2 min and retry; report if persistent |
| GHA workflow dispatch race (run ID not found) | Wait 15s and retry `gh run list` |
| Dry-run workflow fails on coordinate guard | pom.xml edit was incorrect — fix and re-push |
| Dry-run workflow fails on `waitUtil` check | Template was corrupted — fix and re-push; verify template source |
| Local build fails with javadoc errors | `failOnError=false` should suppress; if still failing, check java version |
| Missing C7 class at content-check time | Record as C7 finding in PUBLISHING.md; do not edit content |
| Skill run record mismatch at pre-commit | Drain stale records (Step B7); re-create fresh record |
| `check_evidence_churn.py` BLOCK | Set `EVIDENCE_RESTAMP_MSG` env var (Step B8); do not add `--no-verify` |
| Pre-commit hook sync needed | `cp scripts/pre-commit-audit.sh .git/hooks/pre-commit` |
| Reference files staged accidentally | `git restore --staged content/reference.aspose.org/**` |

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
