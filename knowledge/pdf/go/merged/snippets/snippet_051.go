func ExampleDocument_ExtractText() {
	doc, err := pdf.Open("testdata/Hello world.pdf")
	if err != nil {
		log.Fatal(err)
	}
	pages, err := doc.ExtractText()
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(strings.TrimSpace(pages[0]))
	// Output: Hello, world!
}