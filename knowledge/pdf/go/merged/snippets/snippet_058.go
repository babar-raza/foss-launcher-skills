func ExampleNewLinkAnnotation() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)

	link := pdf.NewLinkAnnotation(page, pdf.Rectangle{LLX: 50, LLY: 700, URX: 300, URY: 720})
	link.SetAction(pdf.NewGoToURIAction("https://pkg.go.dev/github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"))
	if err := page.Annotations().Add(link); err != nil {
		log.Fatal(err)
	}
	fmt.Println("annotations:", page.Annotations().Count())
	// Output: annotations: 1
}