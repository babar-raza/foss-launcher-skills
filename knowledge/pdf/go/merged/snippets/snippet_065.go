func ExampleMarkdownToDocumentFromStream() {
	md := "# Hello\n\nA paragraph with **bold** text.\n"
	doc, err := pdf.MarkdownToDocumentFromStream(strings.NewReader(md))
	if err != nil {
		log.Fatal(err)
	}
	pages, _ := doc.ExtractText()
	fmt.Println(strings.Split(pages[0], "\n")[0])
	// Output: Hello
}