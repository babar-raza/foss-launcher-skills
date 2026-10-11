table := pdf.NewTable().
    SetColumnWidths([]float64{100, 200, 80, 80}).
    SetBorder(pdf.BorderInfo{Sides: pdf.BorderSideAll, Width: 1}).
    SetRepeatingRowsCount(1)

header := table.AddRow()
header.AddCells("Product", "Description", "Qty", "Total")

for _, item := range invoiceItems {
    row := table.AddRow()
    row.AddCells(item.Name, item.Description, item.Qty, item.Total)
}

// Summary row: "TOTAL" label spans the first 3 columns, amount in column 4.
totals := table.AddRow()
totals.AddCell("TOTAL").SetColSpan(3).SetHAlign(pdf.HAlignRight)
totals.AddCell(fmt.Sprintf("€%.2f", grandTotal))

pagesAdded, _ := page.AddTable(table, pdf.Rectangle{LLX: 50, LLY: 100, URX: 510, URY: 750})
fmt.Printf("table flowed to %d additional pages\n", pagesAdded)
