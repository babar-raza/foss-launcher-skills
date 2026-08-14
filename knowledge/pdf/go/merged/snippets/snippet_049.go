func ExamplePage_AddImage() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	rect := pdf.Rectangle{LLX: 50, LLY: 50, URX: 300, URY: 300}
	if err := page.AddImage("testdata/Koala.jpg", rect); err != nil {
		log.Fatal(err)
	}

	var buf bytes.Buffer
	if _, err := doc.WriteTo(&buf); err != nil {
		log.Fatal(err)
	}
	fmt.Println("ok")
	// Output: ok
}