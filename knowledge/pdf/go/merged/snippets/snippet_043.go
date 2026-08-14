func ExampleNewDocumentFromFormat() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	size, _ := page.Size()
	fmt.Printf("%.0fx%.0f pt\n", size.Width, size.Height)
	// Output: 595x842 pt
}