func ExampleDocument_Outlines() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)

	item := pdf.NewOutlineItemCollection(doc)
	item.SetTitle("Chapter 1")
	item.SetDestination(pdf.NewDestinationFit(page))
	if err := doc.Outlines().Add(item); err != nil {
		log.Fatal(err)
	}

	fmt.Println(doc.Outlines().Count(), doc.Outlines().At(0).Title())
	// Output: 1 Chapter 1
}