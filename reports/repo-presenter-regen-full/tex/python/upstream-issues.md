# Upstream issues — Aspose.TeX FOSS for Python

Verified: 2026-08-13 against https://github.com/aspose-tex-foss/Aspose.TeX-FOSS-for-Python
(PyPI publication status independently re-checked live against `pypi.org/pypi/aspose-tex/json`
and `pypi.org/pypi/aspose-tex-foss/json` — both return HTTP 404. The packaging defect below was
independently reproduced directly against this checkout — a real `import aspose_tex` attempt,
plus an `ast.parse()` sweep of every `.py` file under `src/aspose_tex/`, plus a real
`pytest --collect-only` run — not merely inferred.)

## Package fails to import entirely — systemic indentation corruption
- **Severity**: BLOCKING
- **Evidence**: `import aspose_tex`
- **Impact**: running the evidence command against this exact checkout raises a real
  `IndentationError` (`expected an indented block after 'for' statement` in
  `src/aspose_tex/_input/catcode.py`). Re-parsing every `.py` file under `src/aspose_tex/`
  independently with `ast.parse()` found 35 of the 45 files fail with a `SyntaxError`/
  `IndentationError` — every nested block body collapses to the same one-space indent regardless
  of true nesting depth, so Python can no longer tell where an inner block ends. Running
  `pytest --collect-only` against the real `tests/` directory confirms the same pattern
  downstream: 67 collection errors against only 2 successfully collected test files. None of the
  Python examples in this README can currently be executed against this exact source snapshot.
- **Not fixable here because**: reconstructing correct indentation for 35 files' worth of nested
  logic from a uniformly-flattened state is not recoverable by inspection or guesswork — it
  requires the upstream maintainer to restore the original source (e.g. from pre-corruption
  history). This candidate's code examples were checked against the real (non-executing) source's
  class/method signatures and docstrings, so they describe the intended API correctly — they
  just cannot run until this is fixed upstream.

## README's own Installation instructions cite a PyPI package that isn't published yet
- **Severity**: BLOCKING
- **Evidence**: `pip install aspose-tex`
- **Impact**: the upstream repository's own README.md lists this exact command as the first
  Installation step, with no caveat. Even setting the packaging defect above aside, this command
  fails on its own terms: no matching release exists on PyPI under either candidate package name
  (confirmed live via a direct PyPI JSON-API check, both returning HTTP 404). A visitor following
  the upstream README literally hits an install failure with no explanation.
- **Not fixable here because**: publishing a release to PyPI is an upstream maintainer action,
  not something a README edit can change. This candidate's own Installation section avoids
  repeating the unpublished command and instead documents the working from-source install path
  (itself currently blocked from running by the packaging defect above, until that is fixed
  upstream).

## Old README's intro paragraph overstates what's currently bundled
- **Severity**: INFORMATIONAL
- **Evidence**: "Computer Modern fonts and hyphenation patterns are bundled"
- **Impact**: Computer Modern font metrics and glyph outlines (`.tfm`/`.pfb`) are genuinely
  bundled under `src/aspose_tex/data/fonts/`, but the bundled `hyphenation/` pattern directory
  contains only a `.gitkeep` placeholder (confirmed by direct listing) and the package's own
  `data/README.md` states US-English patterns "will be added" — not yet present. The `\patterns`
  and `\hyphenation` primitives are registered as no-ops (`_engine/expansion.py`) that parse and
  discard their argument rather than loading real pattern data. No automatic hyphenation
  currently occurs.
- **Not fixable here because**: this is a real, current gap in the upstream package's own bundled
  data, not a README-only inaccuracy that a wording change alone can resolve. This candidate's
  own Intro paragraph and Scope and Limitations section describe the bundled-fonts fact
  accurately and disclose the hyphenation gap explicitly, rather than repeating the old claim.
