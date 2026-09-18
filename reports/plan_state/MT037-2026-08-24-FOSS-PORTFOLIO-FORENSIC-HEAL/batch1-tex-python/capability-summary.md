# tex/python (aspose-tex) — Capability Summary (unaided repo read, 2026-08-25)

Pinned commit: 2f4bfab3863e66ef32868f5464685eb4c2d36911 (matches knowledge/tex/python/merged/model.yaml)

## What the repo actually is

Pure-Python TeX/LaTeX processing library (`aspose_tex`, PyPI name `aspose-tex`,
version 26.5, MIT license, bundled Computer Modern fonts under a separate
LICENSE-FONTS). README explicitly states: "Status: Pre-Alpha. The core engine
and public API are under active development. Interfaces may change between
releases." classifiers confirm "Development Status :: 2 - Pre-Alpha". No
runtime third-party dependencies (dev-only extras: pytest, ruff, build, twine).
requires-python >=3.10.

## Real public API surface (from src/aspose_tex/__init__.py's __all__)

TeXJob, TeXOptions, OutputDevice (ABC), DviDevice, PdfDevice, SvgDevice,
OutputFormat (enum: DVI/PDF/SVG), InputSource (ABC), FileInputSource,
StringInputSource, create_input_source(), __version__.

Exceptions (exceptions.py, not in __all__ but public by convention):
AsposeTeXError (base), InputError, EngineError, FontError.

TeXOptions fields: job_name, magnification, extra_font_paths, load_format
(bool|str|None, default "plain"), extra_format_paths.

**Critical, source-documented limitation**: TeXOptions.load_format's own
docstring states: "In the current M3 workstream, pass False for runnable
M2-style documents until the remaining Plain TeX cascade lands." I.e. the
DEFAULT (`load_format="plain"`) is explicitly flagged by the source itself as
not-yet-reliable; `load_format=False` is the currently-necessary workaround.

## CRITICAL machinery finding: the pinned source does not compile

Verified directly (unaided, no system-tooling): `import aspose_tex` fails
immediately with `IndentationError` in `_input/catcode.py` (a `for` loop body
is not indented deeper than the `for` statement itself). A full
`py_compile` sweep of every .py file in the package shows **35 of 45 files
fail to compile** with the identical defect class (missing extra indent after
a function/if/for header) -- including `presentation/__init__.py`, the module
that defines the ENTIRE public API (TeXJob, TeXOptions, all three output
devices). Confirmed this is not a local clone-cache corruption: `git status`
in the clone is clean, and `git show HEAD:<path>` (reading the git object
database directly) reproduces the identical broken indentation byte-for-byte
in the working tree. HEAD in the clone exactly matches the knowledge model's
pinned repo_sha. This means, as currently pinned, the product's entire
documented public API cannot be imported at all -- not a subtle behavioral
gap, a hard `IndentationError` before any user code can run.

Consistent with this: `data/package_registry.json` confirms
`tex/python.verification.published: false` -- the package has never actually
been published to PyPI (backfill-scanned 2026-08-01, no live match for any
candidate name). A pre-alpha, never-published, non-compiling library is an
internally consistent picture of "very early, unfinished software" -- but
none of the generated content discloses the non-compiling state, and most of
it (see content findings) presents confident, unqualified "just run this"
examples.

## Font/engine internals that exist but are private (not part of the public API)

`_engine/expansion.py:Expander`, `_engine/par_primitives.py:exec_par`,
`_engine/dimparser.py:parse_dimen/parse_glue/parse_integer`,
`_fonts/pfb_parser.py:parse_pfb/PfbData`, `_fonts/tfm_parser.py:parse_tfm/TfmData`,
`_fonts/font_manager.py:FontManager`, `_fonts/encoding.py:FontEncoding`,
`_fonts/font_metrics.py` (FontMetrics), `_input/reader.py:InputReader` -- all
real, all confirmed present in source, all live under underscore-prefixed
"private" packages and are NOT re-exported from the top-level `__init__.py`.
A user cannot `from aspose_tex import Expander` etc.; reaching them requires
importing the private submodule directly, which the content never shows and
which violates the normal underscore-prefix-means-private convention this
same repo's own skill docs (new-docs-page.md/new-kb-howto.md) explicitly
codify elsewhere (font/python's MT028 fix, TC-01, addressed exactly this
class of issue for a different product).
