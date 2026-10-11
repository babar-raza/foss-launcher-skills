func ExampleDocument_WriteHTML() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	_ = page.AddText("Hello HTML", pdf.TextStyle{Size: 18},
		pdf.Rectangle{LLX: 50, LLY: 700, URX: 545, URY: 780})

	var html bytes.Buffer
	if err := doc.WriteHTML(&html, pdf.HTMLSaveOptions{Mode: pdf.HTMLModeText}); err != nil {
		log.Fatal(err)
	}
	fmt.Println("has text spans:", bytes.Contains(html.Bytes(), []byte("<span")))
	// Output: has text spans: true
}