# Upstream Issues — cells/go

## Stale Go-version and dependency claims in the original README

- **Severity**: INFORMATIONAL
- **Evidence**: `go.mod` declares `go 1.24.5` and `go.sum` is empty (zero third-party
  dependencies); `crypto.go` imports only the Go standard library (`crypto/aes`, `crypto/cipher`,
  `crypto/rand`, `crypto/sha512`). The original README and `doc.go` both state "Requires Go
  1.18+" and describe a dependency on "`golang.org/x/crypto`", neither of which matches the
  current source. This candidate states the corrected values (Go 1.24.5+, zero third-party
  dependencies) instead of repeating the stale claim.

## examples/go.mod has an invalid version string, breaking builds under examples/

- **Severity**: BLOCKING
- **Evidence**: `require github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26 v0.0.0` in
  `examples/go.mod` fails `go build ./...` (reproduced live with go1.26.4) with `go: errors
  parsing go.mod: go.mod:5: require github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26:
  version "v0.0.0" invalid: should be v26, not v0`. Editing that version to a valid
  major-version-26 pseudo-version (confirmed working: `v26.0.0-00010101000000-000000000000`)
  resolves it — the `replace ... => ../` directive in the same file already points at the local
  module, so the version string only needs to satisfy Go's syntax check, not resolve to a real
  published release. This does not affect the root module's own `go test ./...`, which passes
  cleanly regardless (confirmed live).

## CSV import does not perform automatic type conversion

- **Severity**: INFORMATIONAL
- **Evidence**: `aspose/cells_foss/csv_handler.go`'s `Worksheet.FromCSV` stores every imported
  field as a Go `string` via `ws.Cells().Set(ref, val)` — no numeric or boolean inference happens
  on import. The original README's "CSV Import/Export — Custom delimiters, automatic type
  conversion" bullet only holds for the export direction (`CellToString`, which does convert
  typed cell values to their CSV string form). This candidate's Key Capabilities and Scope and
  Limitations sections describe the asymmetry accurately instead of repeating the overstated
  claim.
