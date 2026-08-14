// From a file path
doc, err := pdf.Open("input.pdf")

// From an io.Reader (stream, HTTP response, etc.)
doc, err = pdf.OpenStream(r)

// Encrypted files: returns ErrEncrypted from plain Open; supply a password
doc, err = pdf.Open("locked.pdf")
if errors.Is(err, pdf.ErrEncrypted) {
    doc, err = pdf.OpenWithPassword("locked.pdf", "secret")
}

// OpenWithPassword also works on plain PDFs (password is silently ignored),
// so it's a safe drop-in for code that doesn't know up front whether the
// input is encrypted. The password is tried as both user and owner.
doc, err = pdf.OpenWithPassword("maybe-encrypted.pdf", "secret")
