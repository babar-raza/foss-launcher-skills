func ExampleDocument_Split() {
	doc, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	parts, err := doc.Split()
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("parts:", len(parts))
	// Output: parts: 4
}