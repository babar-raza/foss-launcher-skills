# Aspose FOSS for Java — Maven Central Publishing Guide Using Sonatype User Token

## 1. Purpose

This guide explains how Aspose FOSS Java product teams can publish public GitHub repositories to Maven Central under the approved Maven Central groupId:

```text
org.aspose
```

The current publishing model is:

```text
The org.aspose namespace owner has Sonatype publishing access.

Product teams do not need separate Sonatype namespace access.

Product teams publish using the approved org.aspose Sonatype user token configured in their GitHub repository secrets or local Maven settings.xml.
```

Sonatype Central Portal requires Maven publishing to use **user token credentials** in `settings.xml`; the username and password are token values generated in Central Portal, not the normal login password. ([The Central Repository Documentation][1])

---

# 2. Important constraint

There is currently no self-service option available to add more users to `org.aspose`.

Therefore:

```text
Product teams cannot publish to org.aspose using their own Sonatype accounts unless those accounts are separately granted org.aspose publishing access by Sonatype.

For now, use the existing org.aspose publisher account’s generated Sonatype user token.
```

The important distinction is:

```text
Sonatype account login:
Used by the namespace owner to manage Central Portal access.

Sonatype user token:
Used by Maven/GitHub Actions to publish artifacts.
```

Do not share the normal Sonatype login password. Use only the generated **user token** for Maven publishing.

OSSRH is no longer the correct path for new publishing; Sonatype says OSSRH reached end of life on June 30, 2025, and publishing has moved to Central Publisher Portal. ([The Central Repository Documentation][2])

---

# 3. Publishing ownership model

Since product teams will manage everything themselves, the workable model is:

```text
You / org.aspose owner:
- Generate the Sonatype Central Portal user token.
- Share the token securely with each approved product team or repo admin.
- Control token rotation.
- Revoke/regenerate token if exposed.

Product team:
- Maintains its public GitHub repo.
- Adds Maven Central-ready pom.xml.
- Adds GitHub Actions workflows.
- Stores the Sonatype token in GitHub Secrets.
- Stores GPG signing secrets in GitHub Secrets.
- Runs the publish workflow.
- Reviews/publishes the deployment in Sonatype Central Portal, if they have Portal access; otherwise they coordinate with the org.aspose owner for the final publish click when autoPublish=false.
```

Because the same token can publish under `org.aspose`, only trusted product teams should receive it.

---

# 4. Credentials used by product teams

Each product repo needs these GitHub Actions secrets:

```text
CENTRAL_USERNAME
CENTRAL_PASSWORD
GPG_PRIVATE_KEY
GPG_PASSPHRASE
```

Meaning:

```text
CENTRAL_USERNAME
The Sonatype Central Portal user-token username generated from the org.aspose publisher account.

CENTRAL_PASSWORD
The Sonatype Central Portal user-token password generated from the org.aspose publisher account.

GPG_PRIVATE_KEY
The armored private key used to sign Maven artifacts.

GPG_PASSPHRASE
The passphrase for the GPG private key.
```

The actual token must not be committed to the repository, added to workflow YAML, pasted into README, or stored in `pom.xml`.

---

# 5. Sonatype token format

Sonatype provides a Maven `settings.xml` snippet like this:

```xml
<server>
  <id>${server}</id>
  <username>SONATYPE_TOKEN_USERNAME</username>
  <password>SONATYPE_TOKEN_PASSWORD</password>
</server>
```

For Aspose FOSS publishing, use a fixed server id:

```xml
<server>
  <id>central</id>
  <username>SONATYPE_TOKEN_USERNAME</username>
  <password>SONATYPE_TOKEN_PASSWORD</password>
</server>
```

The matching Maven plugin setting must be:

```xml
<publishingServerId>central</publishingServerId>
```

Do not use:

```xml
<id>${server}</id>
```

unless your build explicitly defines and resolves that variable. The simplest and safest standard is:

```text
central
```

Sonatype’s Maven publishing documentation uses this same `central` server id pattern with token credentials. ([The Central Repository Documentation][1])

---

# 6. Local `settings.xml` for authorized publishers

If a product team publishes locally, configure:

```text
~/.m2/settings.xml
```

Windows path:

```text
C:\Users\<UserName>\.m2\settings.xml
```

Linux/macOS path:

```text
~/.m2/settings.xml
```

Example:

```xml
<settings>
  <servers>
    <server>
      <id>central</id>
      <username>SONATYPE_TOKEN_USERNAME</username>
      <password>SONATYPE_TOKEN_PASSWORD</password>
    </server>
  </servers>
</settings>
```

Replace the placeholders with the real token values shared through the approved secure channel.

Do not commit this file.

---

# 7. Base64 token warning

Sonatype may also show a base64 form of:

```text
username:password
```

That is not encryption. It is just encoded text. Treat it as the same secret.

Do not put the base64 value in:

```text
README
workflow YAML
pom.xml
GitHub issue
email thread with broad audience
Teams/Slack/chat
logs
documentation
```

---

# 8. Official Aspose FOSS GPG signing key

The official public signing key is already created and published.

```text
Signing identity:
Aspose FOSS Release Signing
Maven Central signing key for Aspose FOSS Java packages
<packages@aspose.org>

Key ID:
E176D5CBCA1DCC62

Full fingerprint:
69B7 B8A7 846A 92E4 91A1 1500 E176 D5CB CA1D CC62

Public key:
release-public-keys/aspose-foss-maven-public-key.asc

Keyserver:
keyserver.ubuntu.com

Public key commit:
8aceffaf9b — chore: add Aspose FOSS Maven Central GPG public signing key
```

Maven Central requires artifacts to be signed with GPG/PGP and include `.asc` signatures. ([The Central Repository Documentation][1])

The public key is safe to share. The private key and passphrase must only be stored as GitHub Secrets or in a secure vault.

---

# 9. GitHub Secrets setup per product repo

Each product team should open its GitHub repo and go to:

```text
Settings
→ Secrets and variables
→ Actions
→ Repository secrets
```

Add:

```text
CENTRAL_USERNAME
CENTRAL_PASSWORD
GPG_PRIVATE_KEY
GPG_PASSPHRASE
```

Recommended repository protections:

```text
Protect main/master.
Require PR review before merge.
Require CI to pass.
Restrict who can edit .github/workflows/*.
Restrict who can create release tags.
Do not allow untrusted contributors to modify release workflows.
```

This is especially important because public GitHub repos with publishing secrets must not allow arbitrary workflow changes to reach the release branch.

---

# 10. Maven coordinate policy

Use:

```xml
<groupId>org.aspose</groupId>
```

Recommended artifact IDs:

```text
aspose-words-foss
aspose-cells-foss
aspose-slides-foss
aspose-pdf-foss
aspose-email-foss
aspose-barcode-foss
aspose-imaging-foss
aspose-diagram-foss
aspose-ocr-foss
aspose-tasks-foss
aspose-note-foss
aspose-page-foss
aspose-psd-foss
aspose-html-foss
aspose-omr-foss
aspose-cad-foss
aspose-3d-foss
aspose-zip-foss
```

Example dependency after publishing:

```xml
<dependency>
  <groupId>org.aspose</groupId>
  <artifactId>aspose-words-foss</artifactId>
  <version>1.0.0</version>
</dependency>
```

---

# 11. Required Maven Central metadata

Each `pom.xml` must include complete metadata.

Example:

```xml
<groupId>org.aspose</groupId>
<artifactId>aspose-words-foss</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>

<name>Aspose.Words FOSS for Java</name>
<description>Open-source Java library for working with Word document formats.</description>
<url>https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java</url>

<licenses>
  <license>
    <name>MIT License</name>
    <url>https://opensource.org/license/mit/</url>
    <distribution>repo</distribution>
  </license>
</licenses>

<developers>
  <developer>
    <id>aspose</id>
    <name>Aspose</name>
    <organization>Aspose</organization>
    <organizationUrl>https://www.aspose.org</organizationUrl>
  </developer>
</developers>

<scm>
  <connection>scm:git:https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java.git</connection>
  <developerConnection>scm:git:https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java.git</developerConnection>
  <url>https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java</url>
  <tag>HEAD</tag>
</scm>
```

Sonatype’s requirements include valid coordinates, project metadata, license metadata, developer information, SCM information, source artifacts, Javadocs, checksums, and signatures. ([The Central Repository Documentation][1])

---

# 12. Full example `pom.xml`

Each product team can start with this and replace product-specific fields.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

  <modelVersion>4.0.0</modelVersion>

  <groupId>org.aspose</groupId>
  <artifactId>aspose-words-foss</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <packaging>jar</packaging>

  <name>Aspose.Words FOSS for Java</name>
  <description>Open-source Java library for working with Word document formats.</description>
  <url>https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java</url>

  <licenses>
    <license>
      <name>MIT License</name>
      <url>https://opensource.org/license/mit/</url>
      <distribution>repo</distribution>
    </license>
  </licenses>

  <developers>
    <developer>
      <id>aspose</id>
      <name>Aspose</name>
      <organization>Aspose</organization>
      <organizationUrl>https://www.aspose.org</organizationUrl>
    </developer>
  </developers>

  <scm>
    <connection>scm:git:https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java.git</connection>
    <developerConnection>scm:git:https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java.git</developerConnection>
    <url>https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Java</url>
    <tag>HEAD</tag>
  </scm>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>11</maven.compiler.release>
  </properties>

  <build>
    <plugins>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>${maven.compiler.release}</release>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-source-plugin</artifactId>
        <version>3.3.1</version>
        <executions>
          <execution>
            <id>attach-sources</id>
            <goals>
              <goal>jar-no-fork</goal>
            </goals>
          </execution>
        </executions>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-javadoc-plugin</artifactId>
        <version>3.10.1</version>
        <executions>
          <execution>
            <id>attach-javadocs</id>
            <goals>
              <goal>jar</goal>
            </goals>
          </execution>
        </executions>
        <configuration>
          <failOnError>false</failOnError>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-gpg-plugin</artifactId>
        <version>3.2.7</version>
        <executions>
          <execution>
            <id>sign-artifacts</id>
            <phase>verify</phase>
            <goals>
              <goal>sign</goal>
            </goals>
            <configuration>
              <gpgArguments>
                <arg>--pinentry-mode</arg>
                <arg>loopback</arg>
              </gpgArguments>
            </configuration>
          </execution>
        </executions>
      </plugin>

      <plugin>
        <groupId>org.sonatype.central</groupId>
        <artifactId>central-publishing-maven-plugin</artifactId>
        <version>0.10.0</version>
        <extensions>true</extensions>
        <configuration>
          <publishingServerId>central</publishingServerId>
          <autoPublish>false</autoPublish>
        </configuration>
      </plugin>

    </plugins>
  </build>

</project>
```

The Central Publishing Maven Plugin is the Sonatype-supported Maven path for publishing through Central Portal; `mvn deploy` creates and uploads the bundle for Portal validation. ([The Central Repository Documentation][1])

---

# 13. GitHub Actions CI workflow

Create:

```text
.github/workflows/ci.yml
```

```yaml
name: CI

on:
  pull_request:
  push:
    branches:
      - main
      - master

permissions:
  contents: read

jobs:
  build-test:
    name: Build and test
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Build and test
        run: mvn -B -ntp clean verify

      - name: Verify Javadocs
        run: mvn -B -ntp javadoc:javadoc
```

This workflow does not publish and does not need secrets.

---

# 14. GitHub Actions publish workflow

Create:

```text
.github/workflows/publish-maven-central.yml
```

```yaml
name: Publish to Maven Central

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Release version, for example 1.0.0"
        required: true
        type: string
  push:
    tags:
      - "v*.*.*"

permissions:
  contents: read

jobs:
  publish:
    name: Build, sign, and publish
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set release version from manual input
        if: github.event_name == 'workflow_dispatch'
        run: |
          mvn -B -ntp versions:set \
            -DnewVersion="${{ inputs.version }}" \
            -DgenerateBackupPoms=false

      - name: Set release version from tag
        if: startsWith(github.ref, 'refs/tags/')
        run: |
          VERSION="${GITHUB_REF_NAME#v}"
          mvn -B -ntp versions:set \
            -DnewVersion="$VERSION" \
            -DgenerateBackupPoms=false

      - name: Set up Java, Maven Central token, and GPG key
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven
          server-id: central
          server-username: CENTRAL_USERNAME
          server-password: CENTRAL_PASSWORD
          gpg-private-key: ${{ secrets.GPG_PRIVATE_KEY }}
          gpg-passphrase: GPG_PASSPHRASE

      - name: Build, test, sign, and publish
        run: mvn -B -ntp clean deploy
        env:
          CENTRAL_USERNAME: ${{ secrets.CENTRAL_USERNAME }}
          CENTRAL_PASSWORD: ${{ secrets.CENTRAL_PASSWORD }}
          GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}
```

`actions/setup-java` can generate the Maven `settings.xml` server entry and import the GPG private key for the workflow run, using the secrets supplied to the action.

---

# 15. How the token is used in GitHub Actions

This part is important.

In the workflow:

```yaml
server-id: central
server-username: CENTRAL_USERNAME
server-password: CENTRAL_PASSWORD
```

These lines tell `setup-java` to create a Maven server entry named `central`.

The actual values come from environment variables:

```yaml
env:
  CENTRAL_USERNAME: ${{ secrets.CENTRAL_USERNAME }}
  CENTRAL_PASSWORD: ${{ secrets.CENTRAL_PASSWORD }}
```

So the workflow file contains no real token value.

The effective generated Maven config becomes equivalent to:

```xml
<server>
  <id>central</id>
  <username>value from GitHub secret CENTRAL_USERNAME</username>
  <password>value from GitHub secret CENTRAL_PASSWORD</password>
</server>
```

That server id matches:

```xml
<publishingServerId>central</publishingServerId>
```

---

# 16. Release process for each product team

## First-time setup

```text
1. Confirm the repo is public.
2. Confirm LICENSE exists.
3. Confirm README exists.
4. Confirm pom.xml uses groupId org.aspose.
5. Confirm artifactId follows aspose-<family>-foss.
6. Add source jar plugin.
7. Add Javadoc jar plugin.
8. Add GPG signing plugin.
9. Add Central Publishing Maven Plugin.
10. Add GitHub CI workflow.
11. Add GitHub publish workflow.
12. Add GitHub Secrets:
    - CENTRAL_USERNAME
    - CENTRAL_PASSWORD
    - GPG_PRIVATE_KEY
    - GPG_PASSPHRASE
13. Run CI.
14. Confirm mvn clean verify passes.
```

## Release

```text
1. Update CHANGELOG.md.
2. Confirm final version, for example 1.0.0.
3. Create tag:
   git tag v1.0.0
   git push origin v1.0.0

4. GitHub Actions publish workflow runs.
5. The workflow runs:
   mvn clean deploy

6. The Central Publishing Maven Plugin uploads the deployment to Sonatype Central Portal.
7. If autoPublish=false, final publishing must be completed in Central Portal.
8. Verify the package appears on Maven Central.
9. Update README with the Maven dependency snippet.
```

With `autoPublish=false`, the package is uploaded and validated, but manual publish is still required in Central Portal. Sonatype documents `autoPublish=true` for publishing automatically after validation, but first releases should use manual publish. ([The Central Repository Documentation][1])

---

# 17. Local commands

Normal developer build:

```bash
mvn -B -ntp clean verify
```

Verify Javadocs:

```bash
mvn -B -ntp javadoc:javadoc
```

Authorized local publish:

```bash
mvn -B -ntp clean deploy
```

Local publish requires:

```text
~/.m2/settings.xml with the Sonatype user token
local GPG private key available
correct GPG passphrase
```

For most product teams, GitHub Actions publishing is better than local publishing because it is repeatable.

---

# 18. README dependency snippet

After the artifact is published, add:

```xml
<dependency>
  <groupId>org.aspose</groupId>
  <artifactId>aspose-words-foss</artifactId>
  <version>1.0.0</version>
</dependency>
```

Add signing information:

```text
Aspose FOSS Java artifacts are signed with the Aspose FOSS Maven Central signing key.

Key ID:
E176D5CBCA1DCC62

Fingerprint:
69B7 B8A7 846A 92E4 91A1 1500 E176 D5CB CA1D CC62

Public key:
keyserver.ubuntu.com
release-public-keys/aspose-foss-maven-public-key.asc
```

---

# 19. Product team checklist

Before first release:

```text
[ ] Repository is public.
[ ] LICENSE exists.
[ ] README exists.
[ ] CHANGELOG.md exists.
[ ] groupId is org.aspose.
[ ] artifactId follows aspose-<family>-foss.
[ ] version is correct.
[ ] POM has name.
[ ] POM has description.
[ ] POM has project URL.
[ ] POM has license metadata.
[ ] POM has developer metadata.
[ ] POM has SCM metadata.
[ ] Source jar is generated.
[ ] Javadoc jar is generated.
[ ] GPG signing plugin is configured.
[ ] Central Publishing Maven Plugin is configured.
[ ] publishingServerId is central.
[ ] autoPublish is false for first release.
[ ] GitHub CI workflow passes.
[ ] GitHub publish workflow exists.
[ ] GitHub secrets are configured.
[ ] No secrets are committed.
```

Before each release:

```text
[ ] CI passes.
[ ] Version is final, not accidental SNAPSHOT.
[ ] Release notes are ready.
[ ] Tag is correct.
[ ] Publish workflow succeeds.
[ ] Sonatype validation passes.
[ ] Deployment is published in Central Portal.
[ ] Package appears on Maven Central.
[ ] README dependency snippet is updated.
```

---

# 20. Common failures

## 20.1 401 authentication error

Likely causes:

```text
CENTRAL_USERNAME is wrong.
CENTRAL_PASSWORD is wrong.
Token was revoked or rotated.
Token was generated from an account without org.aspose publishing access.
server-id does not match publishingServerId.
GitHub secrets are missing or misnamed.
```

Fix:

```text
Confirm server id is central.
Confirm publishingServerId is central.
Regenerate the Sonatype user token from the org.aspose publisher account.
Update GitHub secrets.
Rerun the workflow.
```

## 20.2 Validation fails because sources or Javadocs are missing

Fix:

```text
Add maven-source-plugin.
Add maven-javadoc-plugin.
Run mvn clean verify.
```

## 20.3 GPG signing fails

Likely causes:

```text
GPG_PRIVATE_KEY is missing.
GPG_PRIVATE_KEY is not armored private key text.
GPG_PASSPHRASE is wrong.
maven-gpg-plugin cannot use loopback pinentry.
```

Fix:

```text
Check GPG_PRIVATE_KEY GitHub secret.
Check GPG_PASSPHRASE GitHub secret.
Keep --pinentry-mode loopback in maven-gpg-plugin.
```

## 20.4 Deployment uploaded but package not visible

If `autoPublish=false`, this is normal. Open Central Portal and publish the deployment manually.

## 20.5 Wrong version published

Maven Central releases are immutable. Sonatype’s guide says a published component cannot be removed, updated, modified, or replaced. Publish a new version instead. ([The Central Repository Documentation][2])

---

# 21. Token rotation policy

Because the same org.aspose token may be used by several product repos, define a simple rotation policy.

Recommended:

```text
Rotate immediately if exposed.
Rotate when a product maintainer leaves.
Rotate every 6 or 12 months.
Keep a record of which repos use the current token.
Update all repo secrets after rotation.
```

When rotating:

```text
1. Generate new Sonatype user token.
2. Update CENTRAL_USERNAME and CENTRAL_PASSWORD in each product repo.
3. Run a test release or dry-run workflow where possible.
4. Revoke old token.
5. Confirm no workflows still use old token.
```

---

# 22. Security rules for public GitHub repos

Because product repos are public:

```text
Do not run publish workflow on pull_request.
Do not expose secrets to forks.
Do not let untrusted contributors change workflow files.
Do not use pull_request_target for publishing.
Do not echo secrets.
Do not print Maven settings.xml.
Do not commit .m2/settings.xml.
Do not commit private GPG keys.
```

Recommended workflow triggers:

```yaml
on:
  workflow_dispatch:
  push:
    tags:
      - "v*.*.*"
```

Avoid:

```yaml
on:
  pull_request:
```

for publishing workflows.

---

# 23. Internal text to share with product teams

```text
Aspose FOSS Java products are published to Maven Central under the official org.aspose groupId.

Because additional users cannot currently be added to the org.aspose namespace through Sonatype Central Portal, product teams will publish using the approved org.aspose Sonatype Central Portal user token.

This token is not a normal login password. It is a Maven publishing token generated from the account that already has org.aspose publishing access.

Each product repository must store the token only in GitHub Actions secrets:

CENTRAL_USERNAME
CENTRAL_PASSWORD

The repository must also store GPG signing secrets:

GPG_PRIVATE_KEY
GPG_PASSPHRASE

No secrets may be committed to the repository, pasted in issues, added to README files, or printed in logs.

All products must use:

groupId: org.aspose
artifactId: aspose-<family>-foss

The Maven server id must be:

central

The Central Publishing Maven Plugin must use:

<publishingServerId>central</publishingServerId>

For first releases, use:

<autoPublish>false</autoPublish>

This uploads and validates the deployment in Sonatype Central Portal before final publishing.
```

---

# 24. What you should send to each product team

Send them three things separately:

## A. This guide

No real secrets inside.

## B. Token values through the approved secure channel

```text
CENTRAL_USERNAME = Sonatype token username
CENTRAL_PASSWORD = Sonatype token password
```

## C. GPG secret setup instructions

```text
GPG_PRIVATE_KEY = armored private key
GPG_PASSPHRASE = passphrase
```

Do not send the private key and passphrase in the same message if avoidable. Store them in GitHub Secrets immediately.

---

# 25. Final recommended setup

Given your constraint, the cleanest practical setup is:

```text
One org.aspose Sonatype user token
Stored as CENTRAL_USERNAME and CENTRAL_PASSWORD in each approved product repo

One official Aspose FOSS Maven signing key
Stored as GPG_PRIVATE_KEY and GPG_PASSPHRASE in each approved product repo

Publishing done by product teams through GitHub Actions
First releases use autoPublish=false
Manual final publish is reviewed in Central Portal
Token rotation handled by org.aspose owner
```

This is not as strong as per-team Sonatype accounts, but if Sonatype does not let you add more users, it is the workable model.

[1]: https://central.sonatype.org/publish/publish-portal-maven/?utm_source=chatgpt.com "Publishing By Using the Maven Plugin - Central Repository"
[2]: https://central.sonatype.org/pages/ossrh-eol/?utm_source=chatgpt.com "OSSRH Sunset - Documentation - Central Repository"


[1]: https://central.sonatype.org/pages/ossrh-eol/ "OSSRH Sunset - Documentation"
[2]: https://central.sonatype.org/register/namespace/?utm_source=chatgpt.com "Register a Namespace - Documentation - Central Repository"
[3]: https://docs.github.com/actions/security-guides/using-secrets-in-github-actions?utm_source=chatgpt.com "Using secrets in GitHub Actions"
[4]: https://central.sonatype.org/publish/requirements/ "Requirements - Documentation"
[5]: https://central.sonatype.org/faq/namespaces-vs-groupids/?utm_source=chatgpt.com "What is the difference between a groupId and a namespace?"
[6]: https://central.sonatype.org/publish/publish-portal-guide/ "Central Publisher Portal Guide - Documentation"
[7]: https://central.sonatype.org/publish/publish-portal-snapshots/ "Publish Portal Snapshots - Documentation"
[8]: https://central.sonatype.org/publish/publish-portal-maven/ "Maven - Documentation"
[9]: https://central.sonatype.com/artifact/org.sonatype.central/central-publishing-maven-plugin?utm_source=chatgpt.com "org.sonatype.central:central-publishing-maven-plugin"
[10]: https://github.com/actions/setup-java?utm_source=chatgpt.com "GitHub - actions/setup-java: Set up your ..."
[11]: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments?utm_source=chatgpt.com "Deployments and environments"
[12]: https://central.sonatype.org/publish/publish-portal-gradle/ "Publish Portal Gradle - Documentation"
