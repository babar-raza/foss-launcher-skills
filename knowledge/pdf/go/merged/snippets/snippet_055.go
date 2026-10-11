func ExampleValidate() {
	report, err := pdf.Validate("testdata/4pages.pdf")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("valid:", report.Valid, "issues:", len(report.Issues))
	// Output: valid: true issues: 0
}