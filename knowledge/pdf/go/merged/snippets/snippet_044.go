func ExamplePage_AddText() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)
	size, _ := page.Size()

	style := pdf.TextStyle{
		Font:   pdf.FontHelveticaBold,
		Size:   24,
		HAlign: pdf.HAlignCenter,
		VAlign: pdf.VAlignMiddle,
	}
	rect := pdf.Rectangle{LLX: 0, LLY: 0, URX: size.Width, URY: size.Height}
	if err := page.AddText("Hello, world!", style, rect); err != nil {
		log.Fatal(err)
	}

	var buf bytes.Buffer
	if _, err := doc.WriteTo(&buf); err != nil {
		log.Fatal(err)
	}
	fmt.Println("wrote:", buf.Len() > 0)
	// Output: wrote: true
}