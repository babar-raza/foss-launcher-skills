func main() {
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	// Build a small sales table.
	headers := []string{"Date", "Product", "Quantity", "Price", "Total"}
	for i, h := range headers {
		ref := string(rune('A'+i)) + "1"
		ws.Cells().Set(ref, h)
	}

	sales := []struct {
		date    string
		product string
		qty     int
		price   float64
	}{
		{"2025-01-15", "Widget A", 10, 12.99},
		{"2025-01-16", "Widget B", 5, 24.50},
		{"2025-01-17", "Gizmo X", 20, 8.75},
		{"2025-01-18", "Widget A", 15, 12.99},
		{"2025-01-19", "Doodad", 8, 39.00},
	}

	for r, s := range sales {
		row := r + 2
		ws.Cells().Set(fmt.Sprintf("A%d", row), s.date)
		ws.Cells().Set(fmt.Sprintf("B%d", row), s.product)
		ws.Cells().Set(fmt.Sprintf("C%d", row), s.qty)
		ws.Cells().Set(fmt.Sprintf("D%d", row), s.price)
		// Total formula — create the cell first with Set, then add the formula.
		eRef := fmt.Sprintf("E%d", row)
		ws.Cells().Set(eRef, nil)
		cell, _ := ws.Cells().Get(eRef)
		cell.SetFormula(fmt.Sprintf("C%d*D%d", row, row))
	}

	// Save as .xlsx.
	xlsxPath := "outputfiles/csv_export_data.xlsx"
	wb.Save(xlsxPath)
	fmt.Printf("Saved workbook to %s\n", xlsxPath)

	// Export to CSV with comma delimiter.
	csvPath := "outputfiles/exported.csv"
	if err := wb.ExportToCSV(0, csvPath, ','); err != nil {
		fmt.Fprintf(os.Stderr, "Error exporting: %v\n", err)
		os.Exit(1)
	}

	// Print the CSV content.
	data, _ := os.ReadFile(csvPath)
	fmt.Printf("Exported to %s:\n", csvPath)
	fmt.Println(string(data))
}