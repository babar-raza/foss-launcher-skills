func ExampleOpen() {
	doc, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(doc.PageCount(), "pages")
	// Output: 4 pages
}