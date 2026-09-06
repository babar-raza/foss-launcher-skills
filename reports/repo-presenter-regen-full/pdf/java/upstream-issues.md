# Upstream issues — Aspose.PDF FOSS for Java

Verified against `runs/.clone_cache/aspose_pdf_java/` (scout SHA `be089a7e5179b3e74776593c929b44f34cd35708`) and `data/package_registry.json`.

## README's Installation section is stale — the package is already published
- **Severity**: INFORMATIONAL
- **Evidence**: the upstream `README.md` says "Maven Central publication is planned but the artifact is **not yet available** on Central" and gives a speculative future snippet for `org.aspose:aspose-pdf:26.7`. `data/package_registry.json`'s `pdf.java` entry records `verification.published: true`, and the real, currently-published coordinates (matching the clone cache's own `pom.xml`, which declares `<groupId>org.aspose</groupId>` / `<artifactId>aspose-pdf-foss</artifactId>` / `<version>26.6.0</version>`) are `org.aspose:aspose-pdf-foss:26.6.0` — a different artifact id and version than the speculative snippet names.
- **Impact**: a developer following the upstream README's own Installation instructions today would build from source unnecessarily, or copy wrong Maven coordinates.
- **Not fixable here because**: this is upstream's own README content; this regenerated candidate already uses the real, live coordinates.

## README's stated JavaDoc output path doesn't match the build config
- **Severity**: INFORMATIONAL
- **Evidence**: the upstream `README.md` says `mvn javadoc:javadoc` output "lives in `target/site/apidocs/`", but `pom.xml`'s `maven-javadoc-plugin` configuration sets `<outputDirectory>${project.build.directory}/apidocs</outputDirectory>` — resolving to `target/apidocs/`, not `target/site/apidocs/`.
- **Impact**: a developer running the documented command and then looking in the documented directory finds nothing there.
- **Not fixable here because**: this is upstream's own README content; this regenerated candidate states the corrected path.

## AGENTS.md's stated Java version is incomplete relative to the real build/CI matrix
- **Severity**: INFORMATIONAL
- **Evidence**: `AGENTS.md`'s "Project at a glance" states only "Language: Java 17", but `pom.xml` sets `<maven.compiler.source>11</maven.compiler.source>` / `<maven.compiler.target>11</maven.compiler.target>` (the real minimum compile target, matching the upstream README's own "Java 11+" badge), and `.github/workflows/build.yml`'s real CI matrix builds and tests on **both** JDK 11 and JDK 17 (`matrix: java: ['11', '17']`). AGENTS.md's single "Java 17" line, read alone, doesn't convey either fact.
- **Impact**: a contributor reading only `AGENTS.md` could assume JDK 17 is the minimum required to build, when JDK 11 actually is (17 is an additional CI-verified target, not the floor).
- **Not fixable here because**: this is upstream's own `AGENTS.md` content; this regenerated candidate states the real minimum (Java 11+) drawn from `pom.xml`.
