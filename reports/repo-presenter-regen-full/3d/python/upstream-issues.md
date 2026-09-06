# Upstream issues — Aspose.3D FOSS for Python

Verified: 2026-08-13 against https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-Python.git @ ab1a2267a0ba6302311d0c7c4ad01494974c7d76
Re-verified: 2026-09-02 against the same repository @ d9f3bfe50d (HEAD) and the published PyPI wheel aspose-3d-foss 26.1.0 (byte-identical to HEAD, 358/358 .py files) -- the four entries at the end were found on that date.

## Four format-options classes imported from the top-level formats package are shadow duplicates, not the real submodule classes

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: Live-reproduced by importing both paths side by side in the same process.
  `from aspose.threed.formats import GltfSaveOptions` and
  `from aspose.threed.formats.gltf import GltfSaveOptions` resolve to two DIFFERENT classes —
  confirmed with a Python identity comparison (false) and an MRO dump: the top-level name
  resolves to a bare, single-file module-level class with no meaningful parent type at all, not
  the real, properly-subclassed submodule class. Constructing the top-level version and
  membership-checking it against the format package's own shared options base type returns
  false, while the same membership check against a submodule-constructed instance returns true.
  The same shadowing pattern applies to the OBJ, STL, and COLLADA load/save option pairs — each
  has a genuine, correctly-subclassed implementation under its own format submodule, re-imported
  and shadowed by a broken duplicate at the top level of the shared formats package. 3MF and FBX
  are unaffected — their top-level and submodule names resolve to the identical class.
- **Impact**: A caller who imports any of the four affected option classes via the shorter,
  shared top-level path (the naturally-discoverable import for anyone browsing that package)
  gets an instance the scene entry point's own membership checks silently reject — the real
  options are discarded and format-default behavior is used instead with no error raised, or a
  missing-attribute error at some later point depending on which fields the calling code
  touches.
- **Not fixable here because**: The shadowing lives in the installed package's own top-level
  `__init__.py` re-export ordering; no README wording can change which class a given import
  statement resolves to. This candidate's own code examples exclusively import every load/save
  options class from its real submodule path, avoiding the trap without needing to explain it in
  every snippet — documented once here and once as a plain caveat in Scope and Limitations.

## glTF's own save-options factory leaves the format unset, unlike the equivalent STL factory

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: Live-reproduced: calling the glTF format's own create-save-options factory
  method returns an options object whose format-reference field is `None`; calling the STL
  format's equivalent factory method on a freshly constructed instance returns an object whose
  format-reference field is already populated with a real format instance. Both factories are
  meant to do the same job for their own format.
- **Impact**: Combining this format's own factory-created options with a stream-based save (no
  filename to fall back on for format detection) leaves nothing for the save path to detect the
  target format from, unlike the equivalent STL pattern.
- **Not fixable here because**: This is a one-line omission in the real factory method inside
  the installed package; no README wording can populate a field a real method leaves unset.

## The COLLADA format submodule has no package-init file, so its top-level-style import resolves to a module, not a class

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: Live-reproduced: `from aspose.threed.formats.collada import ColladaExporter`
  raises `TypeError: 'module' object is not callable` the moment the imported name is
  instantiated, because Python resolves the bare name to the `ColladaExporter.py` file itself
  (an implicit namespace-package submodule reference) rather than the class defined inside it.
  Confirmed by directory listing: every sibling format submodule (`obj/`, `stl/`, `gltf/`,
  `threemf/`, `fbx/`) has its own `__init__.py` re-exporting its classes; the `collada/`
  directory has none.
- **Impact**: The natural-looking import shape that works for every other format submodule
  (`from aspose.threed.formats.<fmt> import <ClassName>`) silently resolves to the wrong object
  for every COLLADA class, with a confusing `TypeError` only surfacing later at use time, not at
  import time.
- **Not fixable here because**: This is a missing file in the installed package's own directory
  structure; no README wording can add it. This candidate's own COLLADA-adjacent content avoids
  the trap by not demonstrating this particular import shape.

## Ten format option-class pairs have no registered plugin, so opening or saving those extensions fails at runtime

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `aspose/threed/formats/__init__.py`'s private plugin-registration routine (its
  final top-level function call) wires up exactly six format plugins (Wavefront, STL, glTF,
  3MF, FBX, and COLLADA). `aspose/threed/FileFormat.py`'s static extension-lookup method's
  if/elif chain recognizes only six extension spellings and falls through to a final bare
  `return None` for anything else — confirmed by reading the whole method. The module-level
  class attributes for the remaining formats sit at class-body scope as bare `= None`
  placeholders and are never reassigned to a real instance anywhere else in that file (grepped
  the whole module for a second assignment — none found). Ten real, importable option-class
  pairs exist under `aspose/threed/formats/` for these unregistered formats — each is a plain
  data-holder with real constructor defaults, confirmed by opening every one of the ten files
  directly. Calling the scene entry point's open/save methods with one of these ten extensions
  raises `RuntimeError: Unable to detect file format from file name: <name>` (traced directly in
  `aspose/threed/Scene.py`); constructing the matching format object directly and passing it in
  instead reaches `aspose/threed/formats/IOService.py`'s exporter/importer lookup, which raises
  `RuntimeError: No exporter found for format: <format>` (or the importer equivalent) since no
  plugin claims it.
- **Impact**: A developer who finds these ten option classes in the public API surface (or in
  `reference.aspose.org`'s generated class index, which lists all of them alongside the six that
  work) and reasonably infers the corresponding formats are supported will hit an immediate
  runtime failure on the first attempt to open or save any of the ten extensions — there is no
  partial support or graceful fallback.
- **Not fixable here because**: This is real Python source in the product's own repository — no
  README wording change can register a plugin or implement an exporter/importer. The project's
  own build brief (root `AGENTS.md`) explicitly instructs the implementing agent to leave
  importer/exporter code abstract for later implementation, confirming this is a known,
  intentional, currently-incomplete state rather than an accidental regression — but the public
  class surface does not disclose that incompleteness to a caller.

## One registered, importable exporter unconditionally fails on save

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: One of the six registered format plugins (`aspose/threed/formats/fbx/`) has a
  real, working tokenizer-based scene reader (confirmed by reading its full parse
  implementation, including binary and ASCII branches) but its paired writer's two public save
  entry points both immediately execute `raise NotImplementedError("FBX export is not
  implemented")` — confirmed by reading the writer module's full 17-line source, which contains
  no logic beyond the two raise statements. Reading a file in this format and then attempting to
  write it back out in the same format fails on the very first call, regardless of scene
  contents.
- **Impact**: A caller who successfully reads a file in this format and expects to round-trip or
  re-save it in the same format will fail immediately — there is no partial or degraded output.
- **Not fixable here because**: This is the real method body in the product's own repository; a
  README cannot implement scene serialization for this writer. The README documents this
  format's read/write asymmetry as a plain product fact instead.

## Saving one particular registered, working format silently fails because of exporter list ordering, not that format's own code

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: Live-reproduced by importing the real package straight from this checkout and
  calling the public scene-save entry point on a minimal one-triangle scene, targeting the sixth
  and final registered format plugin's own extension. The call raises before reaching that
  plugin's own writer at all:

  ```
  File ".../aspose/threed/Scene.py", line 180, in save
      exporter = io_service.create_exporter(detected_format)
  File ".../aspose/threed/formats/IOService.py", line 52, in create_exporter
      if exporter.supports_format(format_type):
  File ".../aspose/threed/formats/Exporter.py", line 14, in supports_format
      raise NotImplementedError("supports_format is not implemented")
  ```

  The registered exporter list's real, confirmed order (read directly off the live
  `IOService` singleton after import) is Wavefront, STL, glTF, 3MF, FBX, then this sixth format,
  last. The lookup walks that list front to back and stops at the first entry whose own
  format-membership check returns true; the fifth entry in that order never overrides its own
  membership check at all (its class only overrides the two save methods, both of which
  themselves always raise — see the entry above), so calling that check unconditionally raises
  before the sixth entry — this format's own real, working writer — is ever reached. Confirmed
  this format's own writer class is itself fully correct by constructing it directly and calling
  it with no other layer involved: it produced 1821 bytes of well-formed output on the first
  try. Import of the same format is unaffected — its reader-side counterpart earlier in the
  list order properly implements its own membership check, so the reader-side lookup never
  reaches the same broken entry. Confirmed the same broken membership check also triggers for
  every OTHER format when saving through a raw stream with a bare, default-constructed options
  object that has no format set on it yet (reproduced directly: a freshly-constructed STL
  options instance, passed to a stream-based save with no filename to fall back on, hits this
  identical error) — with nothing to match against, every real exporter's own membership check
  correctly returns false and the walk still reaches the same broken entry before giving up.
  Filename-based saves, and saves whose options are built through the target format's own
  factory method, are unaffected, since both paths always resolve a real format value before
  the exporter walk begins.
- **Impact**: Every attempt to save a scene to this one format through the public, documented
  scene-save entry point fails immediately with an unrelated-looking error, regardless of scene
  content — a caller has no indication from the error text alone that the actual cause is an
  unrelated, unimplemented format elsewhere in the registration order, not a defect in the
  format they're trying to save.
- **Not fixable here because**: This is a real ordering interaction between two other files in
  the product's own repository (the lookup routine and the fifth-registered format plugin's own
  class); a README cannot reorder a private registration list or implement another format's
  membership check. The affected format's own read/write asymmetry is documented as a plain
  product fact instead.

## This repo's own knowledge-extraction format table disagrees with the real registered-plugin set, in both directions

- **Severity**: INFORMATIONAL
- **Evidence**: `knowledge/3d/python/merged/formats.md` (an artifact of this repo's own
  knowledge-extraction tooling, not part of the upstream product repository) marks the
  export-only writer named in the entry above as fully round-trip capable, and separately marks
  the one format whose exporter is real and independently confirmed working (a compressed
  package format with real ZIP/XML read-write logic, ~600 combined lines across its reader and
  writer) as entirely unsupported in both directions — the opposite of its real, verified
  behavior. It also marks several of the ten never-registered formats from the first entry above
  as supported, and lists a few short, non-file-format tokens as if they were importable/
  exportable formats in their own right.
- **Impact**: None directly to a library user; this is an internal knowledge-extraction artifact
  consumed by this repo's own tooling, not shipped to the public README (this candidate's
  diagram and Key Capabilities were independently verified directly against clone-cache source,
  not against this file).
- **Not fixable here because**: This table is regenerated by a separate knowledge-extraction
  skill, out of scope for a README edit; logged here only because it is the same
  "declared-but-not-implemented, and declared-as-unsupported-but-actually-working" defect shape
  already documented for a sibling product in this same family, and worth a maintainer's
  attention the next time the knowledge pipeline re-runs for this product.

## Saving to OBJ through the public scene-save entry point always fails: the OBJ writer writes text into the binary stream the save path opens

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: Live-reproduced against the published PyPI wheel 26.1.0 (installed into a fresh
  virtual environment) and identical at repository HEAD d9f3bfe: a minimal scene with one
  primitive mesh saved through the public scene-save entry point to a `.obj` filename raises
  `TypeError: a bytes-like object is required, not 'str'` from
  `aspose/threed/formats/obj/ObjExporter.py`, line 50 (`stream.write(content)` inside
  `_write_obj`). The save path opens the destination file in binary mode; the STL, glTF, GLB,
  and 3MF writers hand it bytes and succeed on the very same scene (all four reproduced clean
  in the same session), while the OBJ writer joins its lines into a `str` and writes that
  directly. No test in `tests/` exercises OBJ export to a path (`test_obj_importer.py` imports
  `ObjExporter` but only reads; `test_plugin_system.py` only instantiates `ObjSaveOptions`), so
  the suite passes with the writer broken.
- **Impact**: Every OBJ export via `Scene.save("<name>.obj")` fails immediately, regardless of
  scene content -- the README's "Position a Node With Transform" example (correct API usage,
  unchanged) currently cannot complete on 26.1.0. OBJ import is unaffected.
- **Not fixable here because**: The fix is inside the product (encode the joined text, or open
  the OBJ destination in text mode); no README wording can make the writer produce bytes. The
  README keeps the correct `Scene.save("post.obj")` usage and documents OBJ export as a plain
  product capability, per the transient-defect rule.

## The published PyPI record points at the wrong repository and carries no license metadata or source distribution

- **Severity**: METADATA-DEFECT
- **Evidence**: Live PyPI JSON for `aspose-3d-foss` 26.1.0
  (https://pypi.org/pypi/aspose-3d-foss/json, probed 2026-09-02): `home_page` /
  `project_urls.Homepage` = `https://github.com/aspose-3d/Aspose.3D-for-Python`, which returns
  HTTP 404 -- the real repository is `aspose-3d-foss/Aspose.3D-FOSS-for-Python` (`setup.py`'s
  `url=` carries the wrong org and repo name); `license` is empty and there is no
  `License-Expression`, although the repository ships an MIT `LICENSE` file; the release contains
  a single `py3-none-any` wheel and no sdist.
- **Impact**: The package page sends readers to a dead link, shows no license, and offers no
  source archive; tooling that resolves a package's repository or license from registry metadata
  (dependency scanners, SBOM generators) gets nothing usable.
- **Not fixable here because**: All three are `setup.py` / release-process facts (`url=`, a
  `license=`/classifier entry, building the sdist the publish workflow already produces); the
  README states the working install command and nothing about the metadata.

## The documented trusted-publisher configuration names a different repository than the one that hosts this code, and the first release has no tag or GitHub Release

- **Severity**: RELEASE-PROCESS
- **Evidence**: `docs/releasing.md` (added in commit 92ba9c24, "Changes for deploying to
  pypi.org") instructs registering the PyPI pending publisher with Owner `aspose-3d` and
  Repository `Aspose.3D-for-Python`; the workflow it triggers, `.github/workflows/publish.yml`,
  lives in `aspose-3d-foss/Aspose.3D-FOSS-for-Python`. PEP 740 trusted publishing verifies the
  exact owner/repository/workflow/environment, so a release published from this repository
  through that workflow will be rejected by PyPI as configured. Consistent with that: the
  repository has no `v26.1.0` tag and no GitHub Release (both checked live 2026-09-02), and the
  workflow has never run -- 26.1.0 was uploaded outside the workflow (the document's own
  "publish the first release manually once" step).
- **Impact**: The next `git tag v<version>` + Release will not publish; the documented release
  procedure cannot currently be followed to completion.
- **Not fixable here because**: The pending-publisher registration on PyPI and the owner/repo
  names in `docs/releasing.md` belong to the project owner; the README links the release process
  document as the repository's own procedure and does not narrate its current state.

