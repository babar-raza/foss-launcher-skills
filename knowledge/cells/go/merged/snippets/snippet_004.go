func main() {
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	// Set up header and data cells.
	ws.Cells().Set("A1", "Fruit")
	ws.Cells().Set("A2", "Apple")
	ws.Cells().Set("A3", "Banana")

	// Create a list-type data validation.
	dv := &cells_foss.DataValidation{
		Type:             cells_foss.DataValidationTypeList,
		Formula1:         `"Apple,Banana,Cherry,Dragonfruit"`,
		AllowBlank:       true,
		ShowErrorMessage: true,
		ErrorTitle:       "Invalid Fruit",
		ErrorMessage:     "Please pick a fruit from the list.",
		ErrorStyle:       cells_foss.ErrorStyleStop,
	}

	if err := ws.AddDataValidation("A2:A10", dv); err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	fmt.Printf("Added %q validation on A2:A10\n", dv.Type)

	// Add a second validation — whole number range.
	dv2 := &cells_foss.DataValidation{
		Type:             cells_foss.DataValidationTypeWhole,
		Formula1:         "1",
		Formula2:         "100",
		ShowErrorMessage: true,
		ErrorTitle:       "Invalid Value",
		ErrorMessage:     "Enter a whole number between 1 and 100.",
		ErrorStyle:       cells_foss.ErrorStyleWarning,
	}
	ws.Cells().Set("B1", "Score (1-100)")
	ws.AddDataValidation("B2:B10", dv2)
	fmt.Println("Added whole-number validation on B2:B10 (1-100)")

	outPath := "outputfiles/data_validation.xlsx"
	if err := wb.Save(outPath); err != nil {
		fmt.Printf("Error saving workbook: %v\n", err)
		return
	}
	fmt.Printf("Workbook saved to %s\n", outPath)
	fmt.Println("Open in Excel — A2:A10 shows a dropdown; B2:B10 accepts 1-100.")
}