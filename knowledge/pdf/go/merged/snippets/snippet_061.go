func ExampleDocument_ReplaceText() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	_ = page.AddText("Draft version. Draft only.",
		pdf.TextStyle{Size: 14}, pdf.Rectangle{LLX: 50, LLY: 700, URX: 545, URY: 780})

	n, err := doc.ReplaceText("Draft", "Final")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("replaced:", n)
	// Output: replaced: 2
}