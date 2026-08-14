doc, _ := pdf.Open("input.pdf")

// 4-up: four source pages per A4 sheet, in a 2×2 grid
nup, _ := doc.NUp(pdf.NUpOptions{
    Rows: 2, Cols: 2,
    Margin: 18, Gutter: 10,
    DrawBorder: true,
})
nup.Save("4up.pdf")

// Booklet: two-up, reordered for saddle-stitch (print double-sided,
// fold, staple — pages read in order). Padded to a multiple of 4.
booklet, _ := doc.Booklet(pdf.BookletOptions{Binding: pdf.BindingLeft})
booklet.Save("booklet.pdf")
