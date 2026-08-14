func main() {
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	// ---- Bold header style ----
	boldStyle := cells_foss.NewStyle()
	boldStyle.Font.Bold = true
	boldStyle.Font.Size = 12

	// ---- Center-aligned style ----
	centerStyle := cells_foss.NewStyle()
	centerStyle.Alignment = &cells_foss.Alignment{
		Horizontal: cells_foss.AlignCenter,
		Vertical:   cells_foss.AlignMiddle,
	}

	// ---- Coloured fill + white text style ----
	highlightStyle := cells_foss.NewStyle()
	highlightStyle.Font.Color = "FFFFFFFF" // white
	highlightStyle.Font.Bold = true
	highlightStyle.Fill = &cells_foss.Fill{
		Type:  cells_foss.FillTypeSolid,
		Color: "FF4472C4", // blue
	}

	// ---- Border style ----
	borderStyle := cells_foss.NewStyle()
	borderStyle.Border = &cells_foss.Border{
		Top:    true,
		Bottom: true,
		Left:   true,
		Right:  true,
	}

	// Populate headers with bold style.
	headers := []string{"Item", "Category", "Price", "In Stock"}
	for i, h := range headers {
		ref := string(rune('A'+i)) + "1"
		ws.Cells().Set(ref, h)
		cell, _ := ws.Cells().Get(ref)
		cell.SetStyle(boldStyle)
	}

	// Populate data rows.
	data := [][]interface{}{
		{"Widget A", "Gadgets", 12.99, true},
		{"Widget B", "Gadgets", 24.50, false},
		{"Gizmo X", "Tools", 8.75, true},
		{"Gizmo Y", "Tools", 15.00, true},
	}

	for r, row := range data {
		rowIdx := r + 2
		for c, val := range row {
			ref := string(rune('A'+c)) + fmt.Sprint(rowIdx)
			ws.Cells().Set(ref, val)
		}
	}

	// Apply styles to data rows.
	for r := 0; r < len(data); r++ {
		rowIdx := r + 2

		// Center the category column.
		cell, _ := ws.Cells().Get(fmt.Sprintf("B%d", rowIdx))
		cell.SetStyle(centerStyle)

		// Highlight rows where In Stock is true.
		stockCell, _ := ws.Cells().Get(fmt.Sprintf("D%d", rowIdx))
		if stockCell.Value == true {
			for c := 0; c < 4; c++ {
				ref := string(rune('A'+c)) + fmt.Sprint(rowIdx)
				cell, _ := ws.Cells().Get(ref)
				cell.SetStyle(highlightStyle)
			}
		}

		// Add border to the last row.
		if r == len(data)-1 {
			for c := 0; c < 4; c++ {
				ref := string(rune('A'+c)) + fmt.Sprint(rowIdx)
				cell, _ := ws.Cells().Get(ref)
				// Merge border with cell's existing style.
				s := cells_foss.NewStyle()
				s.Border = &cells_foss.Border{
					Top: true, Bottom: true, Left: true, Right: true,
				}
				cell.SetStyle(s)
				_ = borderStyle
			}
		}
	}

	outPath := "outputfiles/style.xlsx"
	if err := wb.Save(outPath); err != nil {
		fmt.Printf("Error saving workbook: %v\n", err)
		return
	}
	fmt.Printf("Workbook saved to %s\n", outPath)
	fmt.Println("Open in Excel to see: bold headers, centre-aligned categories,")
	fmt.Println("blue-highlighted in-stock rows, and bottom border.")
}