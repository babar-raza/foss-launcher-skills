doc, _ := pdf.Open("input.pdf")

// Total page count
fmt.Println(doc.PageCount())

// Dimensions of every page (width and height in points, 1/72 inch)
sizes, err := pdf.PageSizes("input.pdf")
for i, s := range sizes {
    fmt.Printf("Page %d: %.1f x %.1f pt\n", i+1, s.Width, s.Height)
}
