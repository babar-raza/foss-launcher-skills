# Upstream Issues — email/python

Verified against `aspose-email-foss` v26.3, repo SHA `c336fa7c1d6b90c6155ecf25a261477640c2b1b6`
(`runs/.clone_cache/aspose_email_python`).

No BLOCKING install/build commands, `NotImplementedError` patterns, or `TODO`/`FIXME`/`XXX`
markers were found anywhere under `aspose/` during verification (a direct grep of the whole
package returned zero matches beyond ordinary `Unsupported ...` runtime-validation error
messages, which are real, intentional format-validation guards, not incomplete features).

One real, non-blocking documentation gap found during composition:

- **`MsgReader.top_level_header` is a real, working public attribute that `PUBLIC_API.md` never
  names.** `MsgReader.__init__` (`aspose/email_foss/msg/reader.py:69`) assigns
  `self.top_level_header` from `parse_top_level_property_stream()`, and the package's own shipped
  example (`examples/msg_reader.py:48`) reads it directly (`reader.top_level_header`). `PUBLIC_API.md`'s
  "Low-Level MSG API" section lists `PropertyStreamHeaderTopLevel` as a "related public type" (the
  type this attribute returns) but never names the attribute itself, and `knowledge/email/python/`'s
  scouted `api_surface.md` omits it too (the scout only picked up `@property`-decorated members,
  not this plain dataclass-adjacent instance attribute assigned in `__init__`). Not a functional
  defect — the attribute works exactly as used in the shipped example — just a real, minor gap
  between the published API summary and what the library's own example script exercises.

No other upstream issues identified during verification.
