func ExampleDocument_Extract() {
	doc, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	out, err := doc.Extract(
		pdf.PageRange{From: 1, To: 2},
		pdf.PageRange{From: 4, To: 4},
	)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("extracted:", out.PageCount(), "pages")
	// Output: extracted: 3 pages
}