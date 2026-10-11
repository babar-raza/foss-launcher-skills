func ExampleDocument_RenderImage() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	_ = page.AddText("Preview me", pdf.TextStyle{Size: 24},
		pdf.Rectangle{LLX: 50, LLY: 700, URX: 545, URY: 780})

	img, err := doc.RenderImage(1, pdf.RenderOptions{DPI: 96})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("rendered:", img.Bounds().Dx() > 0 && img.Bounds().Dy() > 0)
	// Output: rendered: true
}