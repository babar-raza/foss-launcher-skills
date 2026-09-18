# 3d/java OBJ/STL published-vs-source executable proof (TC-RDR-03-3D-JAVA)

While reviewing 3d/java's candidate against the real upstream README, both make a specific,
checkable claim: "OBJ import does not currently work" (upstream) / "OBJ import has a real,
working parser in the upstream GitHub source, but the currently published Maven Central artifact
was built from an older state and still ships a stub there" (candidate, more precise). Given
this session's own G-52 finding (a "doesn't work" claim can be false), this was independently
re-verified with executable proof rather than trusted either way.

## Method

Two separate builds were tested with the same test program (`ObjProof.java`/`StlProof.java`):

1. **Source build**: `mvn compile` against the pinned clone (`e308de58`, 2026-08-11), classes at
   `runs/.clone_cache/aspose_3d_java/target/classes/`.
2. **Published build**: the real `org.aspose:aspose-3d-foss:26.5.0` jar fetched live from Maven
   Central via `mvn dependency:get`, extracted to `published_jar_extract/`.

Both run the identical `Scene.fromFile("x.obj")` public API against a hand-authored, independent
OBJ fixture (a single triangle, not produced by this library).

## Result

| | Source build | Published Maven Central jar (26.5.0) |
|---|---|---|
| OBJ import | Real, working parser — 3 vertices / 1 face loaded correctly | **Stub — returns an empty scene (0 child nodes)** |
| OBJ export | No-op stub (0-byte output), both builds | No-op stub (0-byte output) |
| glTF import | Stub — empty scene, both builds | Stub — empty scene |
| STL import | Real, working — both builds | Real, working — 3 vertices / 1 face |
| STL export | Real, working — both builds | Real, working — 134-byte valid STL |

**Verdict: the candidate's claim is accurate and independently confirmed, not changed.** The
GitHub source (`FileFormat.java`'s package-private `ObjReader`) genuinely has a real, working OBJ
parser — but the Maven Central artifact real users actually install (`26.5.0`) was built from an
older source state that still has the stub. This is exactly the nuance the candidate's own
Scope and Limitations already states; the plainer upstream README claim ("OBJ import does not
currently work") is true for what matters (the published package) but omits the source/package
divergence. STL import and export both genuinely work in every build tested, confirming "STL is
the only fully functional read/write path in this edition."

## Files

`ObjProof.java`, `StlProof.java` — the test programs. Run against both the source-compiled
classes and the extracted published jar (`published_jar_extract/`, `published_build/` — not
checked in, reproducible via `mvn dependency:get -Dartifact=org.aspose:aspose-3d-foss:26.5.0`).
