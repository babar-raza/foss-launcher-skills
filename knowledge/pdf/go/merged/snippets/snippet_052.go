func ExampleDocument_AddSVGWatermark() {
	doc, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	if err := doc.AddSVGWatermark("testdata/aspose-logo.svg"); err != nil {
		log.Fatal(err)
	}
	var buf bytes.Buffer
	if _, err := doc.WriteTo(&buf); err != nil {
		log.Fatal(err)
	}
	fmt.Println("watermarked:", buf.Len() > 0)
	// Output: watermarked: true
}