# C12 final promotion gate decision — it-0014-20260906T1103Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C12 "Java runner"
Commits: `8f3941a2f2` (original, REJECTED), `fad43671a5` (round-1 fix,
independently re-reviewed, REJECTED again for 2 more bugs), `1fa2cf2205`
(round-2 fix), `c0450e8393` (round-3 fix + explicit heuristic-scope
disclosure, merge-reconciled with a concurrent unrelated PR)

## Summary across all rounds

`JavaRunner` (the third concrete `runners/base.py` `LanguageRunner`, after
Go and .NET) went through **three rounds of independent review**, each
finding real, reproducible bugs in the same small area --
`_wrap_fragment`/`_class_name_for`/`_strip_comments`, the functions that
decide how to turn a bare code fragment into compilable Java and what to
name the generated file:

- **Round 1** (REJECT): imports indented into the generated method body
  (illegal Java); wrong class name picked from a helper-class-before-
  public-class block; a `class X` mention inside a `//` comment
  suppressing correct wrapping.
- **Round 2** (REJECT): a leading `/* ... */` block comment (not just `//`)
  stopping import-hoisting early; a string literal containing `/*` with
  no real closer of its own letting the comment-stripping regex span to
  an unrelated, later real `*/`, corrupting class-name detection.
- **Round 3** (this round's fixes): the round-2 hoisting fix over-hoisting
  a same-line `/* comment */ code;` line, silently dropping the trailing
  code; a `class X` mention embedded inside a Java 15+ text block's own
  content, invisible to round 2's literal-PRESERVING fix but still visible
  to the class-detection scan (fixed by neutralizing literal content with
  a placeholder instead of preserving it verbatim).

Every fix across all three rounds was reproduced live BEFORE being
declared fixed, and every fix was mechanically re-verified by reverting it
via `git stash`, confirming the specific new regression test fails for the
claimed reason, then restoring it -- never just trusted on inspection.

Given three consecutive rounds of real bugs in the same narrow area, this
iteration also added an explicit, honest disclosure to `JavaRunner`'s own
class docstring: these are line/regex-based Java-shape heuristics, not a
real grammar parser, proven against every realistic Quick Start snippet
shape found across all three rounds but not proven against every
conceivable Java syntax (annotated class declarations, records, sealed
classes, nested-class-first blocks). A genuinely complete fix needs a real
tokenizer -- out of scope for this taskcard. This is the SAME "disclosed,
accepted scope limit" pattern already used elsewhere in this module (no
real product JAR acquisition, no published/`mvn dependency:get` branch),
just applied to a residual-risk area discovered through review rather than
scoped out from the start.

## Tests

`test_example_verification_java.py` grew from 18 (original) to 26 (final),
picking up one or two real, non-mocked regression tests per round, each
proven to fail against the immediately-prior code and pass against the
fix. All 26 real (`mvn`/`javac`/`java` subprocess) tests green at final
HEAD. `check_monkeypatch_lint.py`: 0 violations across every round.

## Deliberately deferred / not touched (unchanged from round 1, disclosed there)

1. `platform_capabilities.yaml`'s "java" `example_verification` site --
   `registry.py`'s `PLATFORM_CONTRACT` isn't in C12's `allowed_paths`.
2. Real product JAR acquisition via `mvn package` (needs a real offline
   Maven mirror fixture, genuinely substantial, separable work -- Maven's
   own build-plugin resolution over the network confirmed live even for a
   trivial project).
3. A real pilot against actual product content (needs item 2 first).

## Disposition

Recommending CLOSE. The core deliverable -- a real, working, tested Java
`LanguageRunner` -- required three real rounds of adversarial scrutiny to
converge, which is exactly what that scrutiny is for; the alternative
(closing after round 1 or round 2) would have shipped a runner with a
confirmed illegal-Java-generation bug or a confirmed wrong-class-name bug
into the next taskcard that consumes it. The residual heuristic-based risk
is now honestly disclosed rather than hidden, with a stated remediation
posture (fix real, reproduced failures the same way; don't preemptively
guess at more). Not spawning a fourth agent-based review round: three
independent passes already converged on "no more bugs found after active
hunting" for round 3's own reviewer request, and continuing indefinitely
risks an unbounded review-fix loop rather than genuine additional
confidence.
