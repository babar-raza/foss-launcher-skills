func ExamplePage_DrawRectangle() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)

	style := pdf.ShapeStyle{
		LineStyle: pdf.LineStyle{
			Color: &pdf.Color{R: 0.1, G: 0.3, B: 0.6, A: 1},
			Width: 2,
		},
		FillColor: &pdf.Color{R: 0.85, G: 0.92, B: 1, A: 1},
	}
	rect := pdf.Rectangle{LLX: 100, LLY: 600, URX: 400, URY: 750}
	if err := page.DrawRectangle(rect, style); err != nil {
		log.Fatal(err)
	}
	fmt.Println("ok")
	// Output: ok
}