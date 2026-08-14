func ExamplePage_WriteSVG() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	_ = page.DrawCircle(pdf.Point{X: 200, Y: 600}, 50,
		pdf.ShapeStyle{FillColor: &pdf.Color{R: 1, G: 0.8, A: 1}})

	var svg strings.Builder
	if err := page.WriteSVG(&svg); err != nil {
		log.Fatal(err)
	}
	fmt.Println("vector output:", strings.Contains(svg.String(), "<svg"))
	// Output: vector output: true
}