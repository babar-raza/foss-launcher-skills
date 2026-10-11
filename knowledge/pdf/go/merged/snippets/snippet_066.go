func ExampleDocument_WriteMarkdown() {
	doc, err := pdf.MarkdownToDocumentFromStream(strings.NewReader("# Title\n\nBody text.\n"))
	if err != nil {
		log.Fatal(err)
	}
	var out strings.Builder
	if err := doc.WriteMarkdown(&out); err != nil {
		log.Fatal(err)
	}
	fmt.Println(strings.Split(out.String(), "\n")[0])
	// Output: # Title
}