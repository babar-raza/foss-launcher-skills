func ExampleImageToDocument() {
	doc, err := pdf.ImageToDocument("testdata/Koala.jpg")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("pages:", doc.PageCount())
	// Output: pages: 1
}