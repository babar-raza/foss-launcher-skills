func ExampleDocument_Rotate() {
	doc, err := pdf.Open("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	if err := doc.Rotate(pdf.Rotate90, 1, 3); err != nil {
		log.Fatal(err)
	}
	p1, _ := doc.Page(1)
	p2, _ := doc.Page(2)
	fmt.Println("page1:", p1.Rotation(), "page2:", p2.Rotation())
	// Output: page1: 90 page2: 0
}