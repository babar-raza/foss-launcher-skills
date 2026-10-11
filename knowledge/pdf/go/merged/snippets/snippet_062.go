func ExampleForm_AddTextField() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	form := doc.Form()
	field, err := form.AddTextField(1, pdf.Rectangle{LLX: 50, LLY: 700, URX: 300, URY: 725}, "customer")
	if err != nil {
		log.Fatal(err)
	}
	_ = field.SetValue("ACME Corp")

	fmt.Println(form.Field("customer").Value())
	// Output: ACME Corp
}