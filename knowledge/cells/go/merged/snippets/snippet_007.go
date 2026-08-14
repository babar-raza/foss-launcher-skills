func main() {
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	// ---- Populate some cells ----
	ws.Cells().Set("A1", "Product Catalog")
	ws.Cells().Set("A3", "Item")
	ws.Cells().Set("B3", "Price")
	ws.Cells().Set("A4", "Widget")
	ws.Cells().Set("B4", "$9.99")

	// ---- Embed a picture ----
	pic := cells_foss.NewPicture(generateSmallPNG(), "png")
	pic.Width = 100
	pic.Height = 80
	pic.SetAnchor(5, 1) // position at row 5, column B

	if err := ws.AddPicture(pic); err != nil {
		fmt.Printf("Error adding picture: %v\n", err)
		return
	}

	fmt.Printf("Added %q at row=%d, col=%d (%d×%d px)\n",
		pic.Name, pic.Row, pic.Col, pic.Width, pic.Height)

	outPath := "outputfiles/picture.xlsx"
	if err := wb.Save(outPath); err != nil {
		fmt.Printf("Error saving: %v\n", err)
		return
	}
	fmt.Printf("Workbook saved to %s\n", outPath)
	fmt.Println("Open in Excel — the image should appear at row 5, column B.")
}