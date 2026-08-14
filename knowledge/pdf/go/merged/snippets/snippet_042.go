func ExampleOpenWithPassword() {
	// Build an encrypted document in memory so the example is self-contained.
	src := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	src.SetEncryption(pdf.EncryptionOptions{UserPassword: "secret"})
	var buf bytes.Buffer
	if _, err := src.WriteTo(&buf); err != nil {
		log.Fatal(err)
	}

	doc, err := pdf.OpenStreamWithPassword(&buf, "secret")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("opened:", doc.PageCount(), "pages")
	// Output: opened: 1 pages
}