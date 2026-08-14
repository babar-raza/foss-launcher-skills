func main() {
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	// Populate a few cells.
	ws.Cells().Set("A1", "Hello")
	ws.Cells().Set("B1", "World")
	ws.Cells().Set("A2", "Answer")
	ws.Cells().Set("B2", 42)

	outPath := "outputfiles/basic.xlsx"
	if err := wb.Save(outPath); err != nil {
		fmt.Printf("Error saving workbook: %v\n", err)
		return
	}
	fmt.Printf("Workbook saved to %s\n", outPath)
}