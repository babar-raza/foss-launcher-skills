table := pdf.NewTable().
    SetColumnWidths([]float64{60, 200, 80, 80}).
    SetRepeatingRowsCount(1)

// Header row with logo image + text headers.
header := table.AddRow().SetBackground(&pdf.Color{R: 0.95, G: 0.95, B: 0.95, A: 1})
header.AddCell("").SetImage("logo.png")
header.AddCell("Product")
header.AddCell("Qty")
header.AddCell("Total")

// Alternating row colors via Row.SetBackground.
rows := table.AddRows([][]string{
    {"", "Widget",   "5", "€25.00"},
    {"", "Gadget",   "2", "€18.00"},
    {"", "Sprocket", "9", "€72.00"},
})
for i, r := range rows {
    if i%2 == 1 {
        r.SetBackground(&pdf.Color{R: 0.97, G: 0.97, B: 0.97, A: 1})
    }
}

page.AddTable(table, pdf.Rectangle{LLX: 50, LLY: 100, URX: 470, URY: 750})
