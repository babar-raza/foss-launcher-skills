func main() {
	wb := cells_foss.NewWorkbook()
	ws := wb.Worksheets[0]

	ws.Cells().Set("A1", "Product Catalog")

	// generateSmallPNG returns a minimal PNG for the example; see
	// examples/picture/main.go for the full helper.
	pic := cells_foss.NewPicture(generateSmallPNG(), "png")
	pic.Width = 100
	pic.Height = 80
	pic.SetAnchor(5, 1) // row 5, column B

	if err := ws.AddPicture(pic); err != nil {
		fmt.Printf("Error adding picture: %v\n", err)
		return
	}

	wb.Save("outputfiles/picture.xlsx")
}
