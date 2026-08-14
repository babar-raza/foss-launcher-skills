func ExampleDocument_SetEncryption() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	doc.SetEncryption(pdf.EncryptionOptions{
		UserPassword:  "secret",
		OwnerPassword: "owner-secret",
		Permissions:   &pdf.Permissions{AllowPrint: true, AllowCopy: true},
		Algorithm:     pdf.EncryptionAlgAES128,
	})

	var buf bytes.Buffer
	if _, err := doc.WriteTo(&buf); err != nil {
		log.Fatal(err)
	}

	// The file is now encrypted; Open returns ErrEncrypted.
	if _, err := pdf.OpenStream(&buf); err != nil {
		fmt.Println("encrypted")
	}
	// Output: encrypted
}