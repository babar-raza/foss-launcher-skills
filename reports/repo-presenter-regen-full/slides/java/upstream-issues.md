# Upstream issues — slides/java

## `Presentation.save(path, format)` silently ignores the requested save format

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `src/main/java/org/aspose/slides/foss/Presentation.java`, lines 747-785. Every
  overload that accepts a save-format enum parameter discards that argument entirely and
  delegates straight to the plain path/stream overload with no validation, no exception, and no
  warning of any kind.
- **Reproduction**: request a save format other than PPTX on any overload that accepts one, and
  inspect the written output — it is still a valid PPTX/OOXML package, not the requested format.
- **Impact**: a caller who intends to guard against accidentally requesting an unsupported export
  format gets no signal that the request was ignored. This is now disclosed as a plain product fact
  in the candidate README's Scope and Limitations section (never as forensic narration), per this
  skill's own "actionable blocking command still needs a plain pointer sentence" rule.
