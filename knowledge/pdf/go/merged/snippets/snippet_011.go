func main() {
	doc, err := pdf.Open("testdata/split/4pages.pdf")
	if err != nil {
		log.Fatalf("open: %v", err)
	}

	doc.ClearInfo()

	printMetadata(doc)
}