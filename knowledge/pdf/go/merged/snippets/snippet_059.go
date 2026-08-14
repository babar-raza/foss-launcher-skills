func ExampleDocument_GenerateTOC() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	doc.AddBlankPageFromFormat(pdf.PageFormatA4)
	body, _ := doc.Page(1)

	chapter := pdf.NewOutlineItemCollection(doc)
	chapter.SetTitle("Chapter 1")
	chapter.SetDestination(pdf.NewDestinationFit(body))
	if err := doc.Outlines().Add(chapter); err != nil {
		log.Fatal(err)
	}

	added, err := doc.GenerateTOC(pdf.TOCOptions{Title: "Table of Contents"})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("TOC pages added:", added, "| total pages:", doc.PageCount())
	// Output: TOC pages added: 1 | total pages: 3
}