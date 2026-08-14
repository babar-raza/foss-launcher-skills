func main() {
	// Create a sample CSV file to import.
	csvContent := "Name,Department,Salary\n" +
		"Alice Chen,Engineering,95000\n" +
		"Bob Smith,Marketing,72000\n" +
		"Carol Davis,Engineering,88000\n" +
		"Dan Wilson,Sales,65000\n"

	csvPath := "outputfiles/employees.csv"
	if err := os.WriteFile(csvPath, []byte(csvContent), 0644); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing CSV: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Created sample CSV: %s\n", csvPath)

	// Import into a new workbook.
	wb := cells_foss.NewWorkbook()

	if err := wb.ImportFromCSV(csvPath, "Employees", ','); err != nil {
		fmt.Fprintf(os.Stderr, "Error importing CSV: %v\n", err)
		os.Exit(1)
	}

	// Verify the imported data.
	ws := wb.Worksheets[1] // second sheet (index 0 is the default "Sheet1")
	fmt.Printf("Imported sheet: %q\n", ws.Name)

	for r := 1; r <= 4; r++ {
		name, _ := ws.Cells().Get(fmt.Sprintf("A%d", r))
		dept, _ := ws.Cells().Get(fmt.Sprintf("B%d", r))
		salary, _ := ws.Cells().Get(fmt.Sprintf("C%d", r))
		fmt.Printf("  %v | %v | %v\n", name.Value, dept.Value, salary.Value)
	}

	// Save as .xlsx.
	xlsxPath := "outputfiles/csv_imported.xlsx"
	if err := wb.Save(xlsxPath); err != nil {
		fmt.Fprintf(os.Stderr, "Error saving: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Saved workbook to %s\n", xlsxPath)
}