func ExampleDocument_Optimize() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	font, err := doc.LoadFont("testdata/DejaVuSans.ttf")
	if err != nil {
		log.Fatal(err)
	}
	page, _ := doc.Page(1)
	_ = page.AddText("Привет, мир!", pdf.TextStyle{Font: font, Size: 18},
		pdf.Rectangle{LLX: 50, LLY: 700, URX: 545, URY: 780})

	res, err := doc.Optimize(pdf.DefaultOptimizationOptions())
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("fonts subset:", res.SubsettedFonts)
	// Output: fonts subset: 1
}