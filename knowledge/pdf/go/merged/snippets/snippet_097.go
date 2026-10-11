// Embed an external SVG file into a page
doc, _ := pdf.Open("input.pdf")
page, _ := doc.Page(1)
page.AddSVG("logo.svg", pdf.Rectangle{LLX: 50, LLY: 700, URX: 250, URY: 800})

// Pre-parse for reuse on many pages
svg, _ := doc.LoadSVG("watermark.svg")
for i := 1; i <= doc.PageCount(); i++ {
    p, _ := doc.Page(i)
    p.AddSVGObject(svg, pdf.Rectangle{LLX: 0, LLY: 0, URX: 595, URY: 842})
}

// Or use the watermark helper (covers all pages with full-MediaBox positioning)
doc.AddSVGWatermark("watermark.svg")
