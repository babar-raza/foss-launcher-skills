func main() {
	// Load the workbook produced by the basic example.
	wb, err := cells_foss.Load("outputfiles/basic.xlsx")
	if err != nil {
		fmt.Printf("Error loading workbook: %v\n", err)
		fmt.Println("Did you run the basic example first? (cd examples && go run ./basic/)")
		return
	}
	defer func() {
		// After a successful save the workbook is clean; any further load
		// will re-read from disk.
		_ = wb
	}()

	ws := wb.Worksheets[0]
	fmt.Printf("Loaded worksheet: %q\n", ws.Name)

	// Read the existing value at A1.
	cell, err := ws.Cells().Get("A1")
	if err != nil {
		fmt.Printf("Error reading A1: %v\n", err)
		return
	}
	fmt.Printf("Original A1 = %v\n", cell.Value)

	// Modify A1.
	if err := ws.Cells().Set("A1", "World"); err != nil {
		fmt.Printf("Error setting A1: %v\n", err)
		return
	}

	// Add a new cell.
	ws.Cells().Set("C1", "New Column")

	outPath := "outputfiles/modified.xlsx"
	if err := wb.Save(outPath); err != nil {
		fmt.Printf("Error saving workbook: %v\n", err)
		return
	}
	fmt.Printf("Modified workbook saved to %s\n", outPath)

	// Verify the change survived the round-trip.
	reloaded, _ := cells_foss.Load(outPath)
	c, _ := reloaded.Worksheets[0].Cells().Get("A1")
	fmt.Printf("Reloaded A1 = %v\n", c.Value)
}