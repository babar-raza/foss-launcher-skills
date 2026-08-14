func main() {
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	// ---- Build a sales table ----
	headers := []string{"Product", "Q1", "Q2", "Q3", "Q4", "Total"}
	for i, h := range headers {
		ref := string(rune('A'+i)) + "1"
		ws.Cells().Set(ref, h)
	}

	products := []struct {
		name string
		q1   float64
		q2   float64
		q3   float64
		q4   float64
	}{
		{"Widget A", 1200, 1350, 1100, 1500},
		{"Widget B", 800, 920, 1050, 880},
		{"Gizmo X", 2400, 2600, 2300, 2800},
		{"Gizmo Y", 600, 750, 690, 820},
		{"Doodad", 1500, 1400, 1600, 1700},
	}

	for r, p := range products {
		row := r + 2
		ws.Cells().Set(fmt.Sprintf("A%d", row), p.name)
		ws.Cells().Set(fmt.Sprintf("B%d", row), p.q1)
		ws.Cells().Set(fmt.Sprintf("C%d", row), p.q2)
		ws.Cells().Set(fmt.Sprintf("D%d", row), p.q3)
		ws.Cells().Set(fmt.Sprintf("E%d", row), p.q4)

		// Add a SUM formula for the Total column.
		totalRef := fmt.Sprintf("B%d:E%d", row, row)
		totalAddr := fmt.Sprintf("F%d", row)
		ws.Cells().Set(totalAddr, nil)
		cell, _ := ws.Cells().Get(totalAddr)
		cell.SetFormula(fmt.Sprintf("SUM(%s)", totalRef))
	}

	// ---- Create a table for the data range ----
	lastRow := len(products) + 1
	rangeRef := fmt.Sprintf("A1:F%d", lastRow)
	tbl := ws.AddTable(rangeRef)
	tbl.HasHeaderRow = true
	tbl.StyleName = "TableStyleMedium6"

	fmt.Printf("Created table %q covering %s (%d columns, %d data rows)\n",
		tbl.Name, tbl.Range, 6, len(products))

	outPath := "outputfiles/table.xlsx"
	if err := wb.Save(outPath); err != nil {
		fmt.Printf("Error saving: %v\n", err)
		return
	}
	fmt.Printf("Workbook saved to %s\n", outPath)
	fmt.Println("Open in Excel — you should see a formatted table with filter buttons.")
}