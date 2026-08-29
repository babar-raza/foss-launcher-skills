// Fixture package: minimal Go source exercising the declaration kinds
// tree_helpers._CLASS_TYPES["go"] / _FUNC_TYPES["go"] / _MODULE_TYPES["go"]
// are expected to handle (TC-MT040-40 declaration-kind census fixture).
package api

// Document represents a document.
type Document struct {
	Path string
}

// Writer defines a save contract.
type Writer interface {
	Save(path string) error
}

// SaveFormat enumerates output formats.
type SaveFormat int

// Output format constants.
const (
	FormatPdf SaveFormat = iota
	FormatDocx
)

// NewDocument creates a Document.
func NewDocument() *Document {
	return &Document{}
}

// Save writes the document to path.
func (d *Document) Save(path string) error {
	return nil
}
