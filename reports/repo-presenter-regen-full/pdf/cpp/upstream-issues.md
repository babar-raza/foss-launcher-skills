# Upstream Issues — pdf/cpp

Findings from a clean-room regeneration pass against `runs/.clone_cache/aspose_pdf_cpp`
(pinned at repo SHA `40858b60e9babbab4865180e00e2db39f2ba27f8`, matching
`knowledge/pdf/cpp/merged/model.yaml`). This file is written for every run, including the clean
case (an absent file would itself be a bug). Two real, disclosed findings this pass, both in the
upstream repository's own shipped `README.md`, neither a defect in the library's actual C++
source.

## Finding 1 — Stated CMake minimum version does not match either real build-configuration file

**Severity**: VERSION-DRIFT.

**Evidence**: The upstream `README.md`'s own Requirements list states `CMake >= 3.22`. The real,
current `CMakeLists.txt` declares `cmake_minimum_required(VERSION 3.20)` at its very first line,
and the real, current `CMakePresets.json` declares `"cmakeMinimumRequired": {"major": 3, "minor":
21, "patch": 0}`. Neither of the two real, load-bearing build-configuration files agrees with the
README's stated `3.22` floor — both require an older CMake than the README claims.

**Impact**: A developer running exactly CMake 3.20 or 3.21 would read the README, conclude their
toolchain is too old, and needlessly upgrade before ever attempting a build that would, in fact,
already succeed. Low severity because it only overstates a requirement (fails safe, in the
direction of "install something you didn't strictly need") rather than understating one.

**Not fixable here because**: This is a discrepancy inside the upstream product repository's own
`README.md` — a file this skill's own candidate regenerates independently but does not write back
to the upstream repo in this pass. The new candidate composed this session uses the real,
verified value (`3.20`, sourced directly from `CMakeLists.txt`) rather than propagating the
unverified `3.22` figure forward.

## Finding 2 — Upstream README's own "not yet wired" scope note is stale; both cited examples are fully implemented

**Severity**: VERSION-DRIFT.

**Evidence**: The upstream `README.md`'s "Scope note" callout (directly under the Features list)
states: "Some facade methods (e.g. `PdfFileEditor` concatenate/split, `PdfFileStamp`
header/footer stamping) ship their public surface but are not yet wired to the engine." Direct
re-verification against the real, current clone-cache source contradicts both of this note's own
named examples. `PdfFileEditor::Concatenate`/`ConcatenateTwo`/`ConcatenateMany` in
`src/public/pdf_file_editor.cpp` have real, working bodies that open both source documents,
import pages via `Document::ImportPagesFrom`, and save the result — not a stub, not an
unimplemented declaration. `PdfFileStamp::AddHeader`/`AddFooter`/`DrawHeader` in
`src/public/pdf_file_stamp.cpp` likewise have real bodies that draw literal Helvetica text onto
each page, per that file's own header comment ("`AddHeader`/`AddFooter`/`AddPageNumber` draw real
Helvetica text into each" page).

**Impact**: A developer who reads the upstream README and takes this note at face value would
avoid two genuinely working, documented facade capabilities — page concatenation/splitting and
header/footer/page-number stamping — believing them unavailable. This is the opposite direction
of Finding 1's impact: here the README undersells real, working functionality rather than
overstating a requirement, which is the more consequential direction for a library evaluator
deciding whether this FOSS edition meets their needs.

**Not fixable here because**: Same as Finding 1 — this is the upstream repository's own shipped
`README.md` text, not something this pass writes back to that repository. The new candidate
composed this session excludes the stale claim (see `content-dispositions.json`'s `u0028` entry)
and instead documents `PdfFileEditor`'s concatenate/split methods and `PdfFileStamp`'s
header/footer/page-number stamping as real, working Key Capabilities, grounded directly in the
`.cpp` bodies cited above.

## Verification-runner scope note

**Severity**: INFORMATIONAL.

Every code example in this candidate's Quick Start and Additional Examples sections traces to a
real, currently-existing header and (where a corresponding smoke test exists in the sampled
`knowledge/pdf/cpp/merged/snippets/` set) a real GoogleTest snippet; where the 100-snippet sample
does not cover a given API (`TextAbsorber`, `PngDevice`, `Document::Encrypt`, `TextBuilder`,
`WatermarkArtifact`, and `Drawing::Graph` all fall outside the sample), each was instead
independently re-verified directly against the real, current clone-cache header — the
higher-priority source per this repo's own source-of-truth hierarchy. No toolchain compile pass
was run against these examples this session (no `clang`/`cmake` invocation), matching this
skill's own documented default-runner scope: every block would report
`BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE` rather than a claimed compile that never happened.
