# Upstream issues — Aspose.HTML FOSS for Python

Verified: 2026-08-13 against `runs/.clone_cache/aspose_html_python/` (repo_sha
`c2356ec872fd7d64c14a0ae8cc043eea1a03847e`, per `knowledge/html/python/merged/model.yaml`).

## No `pip install` variant succeeds — broken build-backend name

- **Severity**: BLOCKING
- **Evidence**: `pyproject.toml`'s `[build-system]` table reads:
  ```toml
  [build-system]
  requires = ["setuptools>=68"]
  build-backend = "setuptools.backends.legacy:build"
  ```
  `setuptools.backends` is not a real module in any released version of setuptools — the real
  legacy-compatible PEP 517 backend is `setuptools.build_meta:__legacy__` (a `__legacy__` object
  inside the `setuptools.build_meta` module, not a separate `backends` subpackage). Confirmed by
  directly reading this repository's own `pyproject.toml` (unchanged from the copy this
  candidate's own knowledge base was built from) and by independent knowledge of setuptools'
  real package layout.
- **Impact**: `pip` resolves and invokes the `[build-system]` table for every install source —
  a local path, an editable local path (`pip install -e .`), or a `git+https` URL — so every one
  of them fails identically with `ModuleNotFoundError: No module named 'setuptools.backends'`
  before any of this package's own code ever runs. This is not specific to editable installs or
  to a particular install source.
- **Real, working install path**: the repository's own `pyproject.toml` already points pytest at
  `src/` directly (`[tool.pytest.ini_options]` sets `pythonpath = ["src"]`), so the test suite
  never depends on the package being pip-installed. The same approach works for normal use: clone
  the repository, `pip install` the one real runtime dependency (`skia-python>=87.0,<145`), and
  add `src/` to `PYTHONPATH` instead of installing the package itself. This candidate's
  Installation and Development and Testing sections document exactly this, in place of any
  `pip install` of the package.
- **Not fixable here**: the broken build-backend string lives in the upstream repository's own
  `pyproject.toml`; a README cannot change another file's contents.

## Broken test fixture import — `tests.test_css.w3c` does not exist

- **Severity**: INFORMATIONAL
- **Evidence**: `tests/test_css/test_w3c_fixture_loader.py` imports `from
  tests.test_css.w3c.conftest import (...)`. No `w3c` directory exists anywhere under
  `tests/test_css/` in this clone (confirmed by directory listing).
- **Impact**: none for any example in this candidate — no README code block exercises this test
  file. A pre-existing gap in the upstream test suite's own fixtures.
- **Not fixable here**: it is the upstream repository's own test infrastructure.

Everything else in this candidate (Installation, Quick Start, Additional Examples, Development and
Testing commands) was checked directly against `pyproject.toml`, `CONTRIBUTING.md`, and
`conftest.py`; no other undisclosed blocking command was found.

Note (not an upstream product defect, disclosed for completeness): the knowledge-extraction
artifact `knowledge/html/python/merged/api_surface.md` records a truncated one-line docstring
("ends in 'e.g.'") for 4 classes (`ProcessingInstruction`, `CommentToken`, `EndTagToken`,
`StartTagToken`) even though the real source docstrings (`src/aspose_html/dom/
_processing_instruction.py:14`, `src/aspose_html/tokenizer/_tokens.py:51/87/111`) are complete,
single-line summaries ending in a real example (e.g. `"A comment token, e.g. \`\`<!-- text -->\`\`."`).
This candidate's API Reference table uses the real, complete source text for all 4 rows. This is a
knowledge-extraction (`repo-scout`) truncation artifact, not a defect in the upstream product repo
itself.
