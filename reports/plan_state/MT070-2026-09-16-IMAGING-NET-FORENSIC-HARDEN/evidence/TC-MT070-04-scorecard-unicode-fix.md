# TC-MT070-04: Fix IMAGING-NET-SCORECARD-UNICODE-001

**Defect** (`backlog/BACKLOG.md`): `readiness_scorecard.py`'s content-volume-parity
section printed a literal `⚠` (U+26A0) with no stdout encoding forced, crashing with
`UnicodeEncodeError` on Windows consoles running the default cp1252 codepage whenever
any subdomain falls >40% below its peer median — a common state for small/young/niche
products (found live during MT068's imaging/net Stage 9 run, worked around that session
with `PYTHONIOENCODING=utf-8`, never fixed). Not imaging-specific: reproducible for any
product on any default-codepage Windows terminal.

**Fix**: replaced the raw glyph with the ASCII `[!]` bracket marker, matching this
script's own existing `[+]`/`[-]` convention used two sections below (H-gates,
checkpoints) — `scripts/pipeline/commands/launch/readiness_scorecard.py:523`.

**Tests**: added `TestParityWarningMarkerIsAsciiSafe` (2 new tests) to
`scripts/pipeline/tests/test_readiness_scorecard.py` — asserts the source carries no
raw U+26A0 glyph, and that the literal marker text round-trips through `cp1252`
encoding without raising. Full suite: 44/44 passed (was 42; 2 new).

**Skill context**: S-49 (launch-product), scope
`scripts/pipeline/commands/launch/readiness_scorecard.py,scripts/pipeline/tests/test_readiness_scorecard.py`
— disposition `bounded-oneoff` per `docs/workflows/gap-escalation.md` (small,
first-occurrence, bounded patch inside an existing skill's own contract).
