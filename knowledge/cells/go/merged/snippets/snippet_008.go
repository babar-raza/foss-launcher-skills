func main() {
	// ---- Step 1: Generate a medium-sized workbook ----
	fmt.Println("Generating test data …")
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	ws.Cells().Set("A1", "ID")
	ws.Cells().Set("B1", "Name")
	ws.Cells().Set("C1", "Score")

	numRows := 500
	for r := 2; r <= numRows+1; r++ {
		ws.Cells().Set(fmt.Sprintf("A%d", r), r-1)
		ws.Cells().Set(fmt.Sprintf("B%d", r), fmt.Sprintf("Item-%d", r-1))
		ws.Cells().Set(fmt.Sprintf("C%d", r), float64((r*17)%100)+1)
	}

	genPath := "outputfiles/streaming_data.xlsx"
	if err := wb.Save(genPath); err != nil {
		fmt.Fprintf(os.Stderr, "Error generating data: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Generated %d data rows in %s\n", numRows, genPath)

	// ---- Step 2: Stream back through the file ----
	fmt.Println("\nStreaming through rows …")

	sr := cells_foss.NewStreamingReader(genPath)
	rowCount := 0
	var totalScore float64

	err := sr.ProcessRows("Sheet1", func(rowIdx int, cells map[string]string) error {
		rowCount++

		// Print header row.
		if rowIdx == 1 {
			fmt.Printf("  Header: %v\n", cells)
			return nil
		}

		// Print first 3 data rows and every 100th row as a sample.
		if rowIdx <= 4 || rowIdx%100 == 0 {
			fmt.Printf("  Row %d: ID=%s, Name=%s, Score=%s\n",
				rowIdx, cells["A"+fmt.Sprint(rowIdx)],
				cells["B"+fmt.Sprint(rowIdx)],
				cells["C"+fmt.Sprint(rowIdx)])
		}

		// Accumulate scores (for a simple aggregate).
		if score, ok := cells["C"+fmt.Sprint(rowIdx)]; ok {
			var s float64
			fmt.Sscanf(score, "%f", &s)
			totalScore += s
		}

		return nil
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error streaming: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("\nStreamed %d rows (header + %d data rows)\n", rowCount, rowCount-1)
	fmt.Printf("Total score: %.0f, Average: %.2f\n", totalScore, totalScore/float64(rowCount-1))
}