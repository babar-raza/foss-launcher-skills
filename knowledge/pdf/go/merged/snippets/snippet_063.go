func ExampleDocument_NewFlow() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	flow := doc.NewFlow(pdf.FlowOptions{})
	flow.AddHeading(1, "Quarterly Report", pdf.TextStyle{})
	flow.AddParagraph("Revenue grew in every region this quarter.", pdf.TextStyle{Size: 11})
	flow.AddList([]string{"North: +12%", "South: +8%"}, false, pdf.TextStyle{Size: 11})

	pages, err := flow.Render()
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("pages:", pages)
	// Output: pages: 1
}