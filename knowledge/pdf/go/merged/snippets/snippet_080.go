doc, _ := pdf.Open("input.pdf")

doc.SetPageLabels([]pdf.PageLabelRange{
    {StartPage: 1, Style: pdf.PageLabelRomanLower},            // i, ii
    {StartPage: 3, Style: pdf.PageLabelDecimal, StartNum: 1},  // 1, 2, 3, ...
    {StartPage: 8, Style: pdf.PageLabelDecimal, Prefix: "A-"}, // A-1, A-2, ...
})

page, _ := doc.Page(1)
fmt.Println(page.Label()) // "i"

doc.Save("labeled.pdf") // doc.ClearPageLabels() removes them
