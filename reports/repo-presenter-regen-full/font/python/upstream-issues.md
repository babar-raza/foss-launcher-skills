# Upstream issues — Aspose.Font FOSS for Python

Verified: 2026-08-13 against the clone cache pinned to `800ea256fec1eec387cba1fc599530cd402ef515`
(https://github.com/aspose-font-foss/Aspose.Font-FOSS-for-Python), plus a live check of
`https://pypi.org/pypi/aspose-font/json` and `https://pypi.org/pypi/aspose-font-foss/json`.

## Package is not yet published to PyPI
- **Severity**: INFORMATIONAL
- **Evidence**: `curl -o /dev/null -w "%{http_code}" https://pypi.org/pypi/aspose-font/json`
  returns `404` (a known-real package, `requests`, returns `200` via the same endpoint as a
  sanity check), and `https://pypi.org/pypi/aspose-font-foss/json` also returns `404`. This
  agrees with `data/package_registry.json`'s own `font.python.verification.published: false`
  (scouted 2026-08-01, `pypi-backfill-scan`) — for this product the registry's `published` flag
  is confirmed live-correct, not stale in either direction.
- **Impact**: `pip install aspose-font` does not work yet. A visitor following a
  copy-pasted `pip install` instruction (as several sibling products' READMEs correctly show)
  would hit a real, immediate failure for this specific product.
- **Not fixable here because**: publication is a maintainer/release action outside this README's
  scope; this candidate's own Installation section discloses the real state (`git clone` +
  `pip install .` from source) rather than presenting an unpublished package as installable.

## `FontConverter` is not re-exported from the top-level `aspose_font` package
- **Severity**: INFORMATIONAL
- **Evidence**: `src/aspose_font/__init__.py` imports and re-exports `FontLoader`, `FontCleaner`,
  `FontSubsetter`, `SmartInstancer`, `WebFontBuilder`, `FontQaReporter`, `AnimationPreviewBuilder`,
  and every font-format class (`TtfFont`, `CffFont`, `Type1Font`, `WoffFont`, `Woff2Font`,
  `EotFont`), but never imports anything from `aspose_font/converter.py` — `FontConverter` and
  `CurveAdapter` are absent from both the import block and `__all__`. Every real usage in the
  test suite (`tests/test_cleaner.py`, `test_converter.py`, `test_fixture_corpus.py`,
  `test_serializer.py`, `test_woff.py`) imports it as `from aspose_font.converter import
  FontConverter`. **Correction after further verification**: this has limited practical impact —
  `Font.convert(self, target)` (`_font_base.py:113`) is a real, fully-supported instance method
  that internally delegates to `FontConverter.convert(self, target)`, so `font.convert(target)`
  on any already-loaded font works with zero extra imports and is the more natural first path a
  developer would reach for; `FontConverter` itself is a real but lower-level, explicit-import
  alternative, not the only door in.
- **Impact**: a developer who specifically tries `from aspose_font import FontConverter` (rather
  than the simpler `font.convert(target)` instance method) gets an `ImportError`. The upstream
  README never shows either the class-level `FontConverter` import or the instance-level
  `font.convert()` method in its own code examples, despite its "Capability Snapshot" table
  advertising "Convert" as a first-class capability.
- **Not fixable here because**: `__init__.py`'s export list is upstream source, not something a
  README edit can change; this candidate's own Key Capabilities and Quick Start sections show
  both the real `font.convert(target)` instance method and the real
  `from aspose_font.converter import FontConverter` submodule import.

## `pyproject.toml`'s unbounded `mcp` extra is incompatible with the real, current `mcp` 2.0.0 release
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `src/aspose_font/mcp.py:6` does `from mcp.server.fastmcp import FastMCP`.
  `pyproject.toml`'s `[project.optional-dependencies]` declares `mcp = ["mcp>=1.0"]` with no upper
  bound. The real, live `mcp` PyPI package's latest release is `2.0.0`
  (`https://pypi.org/pypi/mcp/json` → `info.version == "2.0.0"`); downloading and inspecting the
  real `mcp-2.0.0-py3-none-any.whl` wheel directly (`zipfile` listing of its contents) confirms
  zero files anywhere named `fastmcp` — the module was renamed from `mcp.server.fastmcp` to
  `mcp.server.mcpserver` in that release (`mcp/server/mcpserver/__init__.py` exists;
  `mcp/server/fastmcp*` does not).
- **Impact**: `pip install ".[mcp]"` with no additional pin can resolve to the real `mcp` 2.0.0,
  which breaks `python -m aspose_font.mcp` at import time with `ModuleNotFoundError: No module
  named 'mcp.server.fastmcp'` — the bundled MCP server surface is unusable until the caller
  independently pins `mcp<2.0`, something neither `pyproject.toml` nor the upstream README states
  anywhere.
- **Not fixable here because**: the `pyproject.toml` dependency bound and the `mcp.py` import path
  are both upstream source, not something a README edit can change; this candidate's own
  Installation section discloses the real, verified `mcp<2.0` pin rather than reproducing the
  upstream README's unpinned `pip install ".[mcp]"` instruction as if it always works.

## No CI workflow file present in this clone snapshot
- **Severity**: INFORMATIONAL
- **Evidence**: `CODEOWNERS` names both `/.gitlab-ci.yml` and `/.github/workflows/` as
  owned paths, but neither exists anywhere in this repository checkout (`find` over the full
  tree returns nothing for either), and the `CHANGELOG.md`'s "Unreleased" entry lists "GitHub
  Actions CI" among artifacts added, but no such workflow file is present at this pinned SHA.
- **Impact**: none for library functionality; this only affects what a consumer-facing README can
  honestly claim. A "Build" status badge cannot be added without linking to a workflow file that
  does not exist in this snapshot.
- **Not fixable here because**: CI configuration is a maintainer/infrastructure concern outside
  this README's scope; this candidate's badge row omits a Build badge rather than link one to a
  nonexistent workflow.

## The upstream README's own "Create a release-safe static instance" Quick Start example raises `ValueError`
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `font.instantiate({"wght": "Bold", "wdth": "Condensed"}, naming_strategy="ribbi-safe", family_suffix="Beta", stat_policy="static")`
  (upstream `README.md`, "Quick Start" -> "Create a release-safe static instance", commit
  `c6d82093` / tree `75a0b491`). Executed live on 2026-09-02 against the repository's own
  `testdata/Roboto-VariableFont_wdth,wght.ttf`: `ValueError: could not convert string to float:
  'Bold'`. Root cause is a documented signature: `TtfFont.instantiate` (`src/aspose_font/ttf/
  font.py:582`) is typed `coordinates: dict[str, float]` and delegates straight to
  `TtfInstancer.instantiate` (float-only); preset-name resolution lives only in
  `SmartInstancer.instantiate` (`src/aspose_font/instancing.py:176`, `dict[str, float | str]`,
  via `resolve()`). The same README's later "Python API Highlights" block uses the working
  `font.smart_instancer.instantiate(...)` form with the identical preset dict, and its
  `font.instantiate({"wght": 700, "wdth": 75}, ...)` example (numeric coordinates) also works.
- **Impact**: a visitor copying the upstream Quick Start's third example hits an immediate
  `ValueError`. Every other Python example in the upstream README executed cleanly against the
  same fixture font (19 of 20 candidate blocks, after this one was corrected).
- **Not fixable here because**: the signature split is upstream API design; this candidate's
  example uses `font.smart_instancer.instantiate(...)` (identical arguments, identical output)
  and states plainly that `font.instantiate(...)` takes numeric coordinates only.
