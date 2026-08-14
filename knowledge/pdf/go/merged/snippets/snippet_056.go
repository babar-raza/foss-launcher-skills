func ExampleNewTable() {
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	page, _ := doc.Page(1)

	table := pdf.NewTable().
		SetColumnWidths([]float64{300, 100}).
		SetDefaultCellBorder(pdf.BorderInfo{Sides: pdf.BorderSideAll, Width: 0.5}).
		SetDefaultCellMargin(pdf.MarginInfo{Top: 4, Right: 6, Bottom: 4, Left: 6})

	header := table.AddRow()
	header.AddCell("Item").SetTextStyle(pdf.TextStyle{Font: pdf.FontHelveticaBold, Size: 11})
	header.AddCell("Price").SetTextStyle(pdf.TextStyle{Font: pdf.FontHelveticaBold, Size: 11}).
		SetHAlign(pdf.HAlignRight)

	table.AddRows([][]string{
		{"Espresso", "€3.50"},
		{"Cappuccino", "€4.50"},
		{"Tiramisu", "€7.50"},
	})

	rect := pdf.Rectangle{LLX: 50, LLY: 500, URX: 450, URY: 750}
	if _, err := page.AddTable(table, rect); err != nil {
		log.Fatal(err)
	}
	fmt.Println("rows:", table.RowCount())
	// Output: rows: 4
}