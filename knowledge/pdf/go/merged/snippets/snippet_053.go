func ExampleDocument_AddTextWatermark() {
	doc, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	style := pdf.TextStyle{
		Font:     pdf.FontHelveticaBold,
		Size:     72,
		Color:    &pdf.Color{R: 0.85, G: 0.85, B: 0.85, A: 0.5},
		Rotation: 45,
		HAlign:   pdf.HAlignCenter,
		VAlign:   pdf.VAlignMiddle,
		Behind:   true,
	}
	if err := doc.AddTextWatermark("DRAFT", style); err != nil {
		log.Fatal(err)
	}
	fmt.Println("ok")
	// Output: ok
}