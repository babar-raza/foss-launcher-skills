# Upstream issues — Aspose.Slides FOSS for C++

Verified: 2026-08-13 against https://github.com/aspose-slides-foss/Aspose.Slides-FOSS-for-Cpp
(repo_sha 25adb25c8796f06d9b89cd5f8093e490091195ef)

## README "Notes" example does not compile — `add_notes_slide()` returns a pointer, not a reference
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: the real README's "Notes" example writes
  `auto& notes = pres.slides()[0].notes_slide_manager().add_notes_slide(); notes.notes_text_frame().set_text(...)`.
  `include/Aspose/Slides/Foss/i_notes_slide_manager.h:19` and
  `include/Aspose/Slides/Foss/notes_slide_manager.h:49` both declare
  `INotesSlide* add_notes_slide()` — a pointer return, not a reference. Binding a non-const
  `auto&` to a prvalue pointer is ill-formed in standard C++, so this exact example does not
  compile as written. Every real integration test that calls this method (e.g.
  `tests/Aspose.Slides.Foss.IntegrationTests/notes_slide_test.cpp`) correctly uses
  `auto* notes = ...` and `notes->notes_text_frame()`.
- **Impact**: a developer copy-pasting the README's own Notes example gets a compiler error on
  the first try.
- **Not fixable here because**: this is upstream README example code, not something a
  downstream candidate README's own content can patch in the real repository; the new candidate
  in this batch uses the correct `auto*`/`->` form instead of reproducing the bug.

## README "Table" example does not compile — `Cell::text_frame()` returns a pointer, not a reference
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: the real README's "Table" example writes
  `table.rows()[0][0].text_frame().set_text("Name");` (dot notation). `Cell::text_frame()` is
  declared `[[nodiscard]] TextFrame* text_frame() noexcept` at
  `include/Aspose/Slides/Foss/cell.h:145` — a pointer, not a reference — so `.set_text(...)` on
  its result does not compile; it requires `->set_text(...)`. Real test snippets
  (`tests/Aspose.Slides.Foss.Tests/*table*`, e.g. `TableIntegrationTest.CellBorders`/`CellFill`)
  consistently use `cell.text_frame()->set_text(...)`.
- **Impact**: same class of defect as the Notes example above — the README's own flagship Table
  snippet fails to compile.
- **Not fixable here because**: upstream example code; the new candidate in this batch uses the
  correct `->` form.

## README "Comments" example does not compile — `add_comment()` takes `Slide&`, the example passes `Slide*`
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: the real README's "Comments" example calls
  `author.comments().add_comment("Review this slide", &slide, PointF{2.0, 2.0}, ...)`, passing
  the address of a `Slide` (a `Slide*`). `CommentCollection::add_comment` is declared
  `Comment& add_comment(const std::string& text, Slide& slide, Drawing::PointF position,
  std::chrono::system_clock::time_point created_time)` at
  `include/Aspose/Slides/Foss/comment_collection.h:35-37` — the second parameter is `Slide&`, not
  `Slide*`, so passing `&slide` is a type mismatch that does not compile. Real test snippets
  (e.g. `tests/Aspose.Slides.Foss.IntegrationTests/comments_test.cpp`) pass the slide reference
  directly: `author.comments().add_comment("Review note", slide, PointF(2.0f, 3.0f), now)`.
- **Impact**: same class of defect — the README's own Comments example fails to compile.
- **Not fixable here because**: upstream example code; the new candidate in this batch passes
  the slide by reference, matching the real signature.

## README overstates `SlideCollection`'s capabilities — no slide-reorder/move method exists
- **Severity**: INFORMATIONAL
- **Evidence**: the real README's Features list claims "Slides — Add, remove, clone, reorder,
  and iterate slides." `include/Aspose/Slides/Foss/slide_collection.h` declares
  `add_clone`/`insert_clone`, `add_empty_slide`, `remove`/`remove_at`, and iteration via
  `begin()`/`end()` — there is no `move`/`reorder`/`swap`/`set_index` method anywhere in the
  class. `insert_clone(index, ...)` can insert a *cloned copy* of a slide at a given position,
  but that is a distinct operation from reordering an existing slide in place.
- **Impact**: a developer relying on the README's claim to look for a slide-reordering API will
  not find one.
- **Not fixable here because**: this is a real gap in the current public API surface, not
  something a README wording fix can resolve; the new candidate in this batch omits the
  "reorder" claim rather than repeating it.
