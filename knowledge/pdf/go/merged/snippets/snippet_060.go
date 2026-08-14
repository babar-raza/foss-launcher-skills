func ExamplePage_SearchText() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	_ = page.AddText("The quick brown fox jumps over the lazy dog.",
		pdf.TextStyle{Size: 14}, pdf.Rectangle{LLX: 50, LLY: 700, URX: 545, URY: 780})

	matches, err := page.SearchText("brown fox")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("%d match: %q\n", len(matches), matches[0].Text)
	// Output: 1 match: "brown fox"
}