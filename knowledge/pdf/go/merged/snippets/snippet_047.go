func ExampleDocument_Append() {
	a, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	b, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	a.Append(b)
	fmt.Println("merged:", a.PageCount(), "pages")
	// Output: merged: 8 pages
}