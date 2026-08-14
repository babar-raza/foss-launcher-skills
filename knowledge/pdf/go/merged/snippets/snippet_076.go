doc, err := pdf.Open("input.pdf")

// Build a new document with pages 1–3 and 7–9 (doc is not mutated)
extracted, err := doc.Extract(
    pdf.PageRange{From: 1, To: 3},
    pdf.PageRange{From: 7, To: 9},
)
extracted.Save("output.pdf")
