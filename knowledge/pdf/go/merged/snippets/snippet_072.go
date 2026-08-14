func ExampleDocument_SetPageLabels() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	_ = doc.AddBlankPageFromFormat(pdf.PageFormatA4)
	_ = doc.AddBlankPageFromFormat(pdf.PageFormatA4)

	err := doc.SetPageLabels([]pdf.PageLabelRange{
		{StartPage: 1, Style: pdf.PageLabelRomanLower},
		{StartPage: 3, Style: pdf.PageLabelDecimal},
	})
	if err != nil {
		log.Fatal(err)
	}
	p2, _ := doc.Page(2)
	p3, _ := doc.Page(3)
	fmt.Println(p2.Label(), p3.Label())
	// Output: ii 1
}