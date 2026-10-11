# C12 promotion gate decision — it-0014-20260906T1103Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C12 "Java runner"

## What shipped this iteration

New `scripts/pipeline/lib/example_verification/runners/java.py`:
`JavaRunner`, the third concrete `runners/base.py` `LanguageRunner`
implementation after C5's `GoRunner` and C11's `DotNetRunner`, applying
both those taskcards' independent-review lessons from the start:

- `canonical_lang = "java"`, `ceiling_tier = 3`.
- `starts_chain`: first non-comment line is `import`/`package`/`class`.
- `acquire`: real toolchain discovery via `mvn -version`, parsing its own
  reported "Java version"/"runtime" line. **Real, machine-confirmed
  wrinkle this designs around** (matching the plan's own explicit
  warning): `mvn` on this machine resolves its own build against JDK
  17.0.19, while the bare `java` directly on PATH is a DIFFERENT JDK,
  21.0.11 -- confirmed live via `mvn -version` before writing any code.
  Uses `shutil.which("mvn")` (never a bare `"mvn"` argv, which raises
  `WinError 2` on Windows since `mvn` resolves to `mvn.CMD` -- also
  confirmed live, the same class of bug the plan warned Go/TypeScript
  already hit once).
- `compile`/`execute`: real `javac`/`java` (NOT full `mvn` per block --
  matching the plan's own `foss-java-publish.md`-derived design: `mvn`
  builds/acquires once, `javac`/`java` do the fast per-block smoke test).
- `classify`: a file-citation-basename check, parameterized by the block's
  own actual generated filename (`{class_name}.java` -- NOT a fixed
  constant like Go's `main.go`/`.NET`'s `Program.cs`, since a block that's
  already a complete `class X` declaration keeps its own name). Verified
  against two REAL, distinct Java diagnostic formats (confirmed via a
  manual probe before writing any code, including a genuine cross-class
  runtime exception): `javac`'s own `<file>.java:<line>:` and a stack
  frame's `(<file>.java:<line>)` -- both distinct from Go's and .NET's own
  formats.

## Tests

New `scripts/pipeline/tests/test_example_verification_java.py` (19 tests,
skipped if `mvn` isn't on PATH, real subprocess calls throughout, ~11s
total): `starts_chain` (4), `classify` unit tests (5), a REAL end-to-end
upstream-error reproduction -- pre-compiles a separate `Lib.class` with a
genuine bug directly into the runner's own work_dir (proving `javac`/
`java`'s implicit cwd-default classpath picks it up, the same way a real
product's already-built classes would sit alongside a block's generated
wrapper), then calls it through `JavaRunner.execute()` for real and
confirms `UPSTREAM-BROKEN` (1), real `acquire()` -- discovers the actual
toolchain, and a genuine `{"ok": False}` when `mvn` is removed from `PATH`
for one call (2), real `compile()` via real `javac` -- clean pass, a
genuine undefined-identifier error, and a complete `class Widget {...}`
block correctly keeping its own class name rather than being force-wrapped
(3), real `execute()` via real `java` -- clean pass and a genuine
divide-by-zero runtime exception (2), and two full
`BaseRunner(JavaRunner(...)).run(...)` end-to-end proofs (2).
`check_monkeypatch_lint.py`: 0 violations.

## Deliberately deferred / not touched (disclosed)

1. **`platform_capabilities.yaml`'s "java" `example_verification` site**
   (in C12's `allowed_paths`) left UNTOUCHED, for the identical reason C11
   disclosed for "net": `check_platform_capabilities.py:
   check_example_verification` does an exact-value diff of the YAML
   against `lib.example_verification.registry.PLATFORM_CONTRACT["java"]`,
   and `registry.py` is NOT in C12's `allowed_paths` -- flipping only the
   YAML side would immediately fail that check.
2. **Real product JAR acquisition via `mvn package`.** `acquire()` never
   puts anything but the block's own generated source file on the
   classpath -- no real product's built library is available to a block
   that references it. This is the SAME class of deferral Go's `go get`
   and .NET's `dotnet add package` branches carry: no fixture to prove it
   against without inventing one. The plan's own "Known extra wrinkle"
   here is real and substantial: Maven's first build resolves its own
   build plugins over the network even for a trivial project (confirmed
   live -- `mvn -o clean package` failed offline on `maven-surefire-plugin`
   even with no tests, since it's bound to the default lifecycle's `test`
   phase regardless; `mvn -o compile` alone succeeds using only
   already-cached plugins). Building the "offline-installable local Maven
   mirror" fixture the plan describes is genuinely separable, substantial
   work -- no `java_offline_mirror` fixture directory was created this
   iteration since nothing yet needs one.
3. **A real pilot against actual product content** (cells/java,
   slides/java, per the plan's own C12 hints). Same reasoning as items 1-2
   above -- needs the real-JAR acquisition this iteration doesn't build.

## Disposition

Recommending CLOSE, pending independent review: the taskcard's core
deliverable (a real, working, tested Java `LanguageRunner`, tier 1-3,
correctly navigating the real JDK-version-mismatch wrinkle the plan warned
about) is built with the design lessons from both prior runners' reviews
already applied from the start. The remaining items are either
structurally blocked outside `allowed_paths` (matching C5/C11 precedent)
or genuinely separable, substantial follow-on work (the offline Maven
mirror), not a corner cut for time.
