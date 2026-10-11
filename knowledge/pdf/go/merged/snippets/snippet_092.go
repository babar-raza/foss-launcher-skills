// Or render a TOC from a supplied list into a region on an existing page.
toc, _ := doc.Page(1)
p2, _ := doc.Page(2)
p5, _ := doc.Page(5)
toc.AddTOC([]pdf.TOCEntry{
    {Title: "Introduction", Level: 0, Page: p2},
    {Title: "Background",   Level: 1, Page: p2},
    {Title: "Conclusion",   Level: 0, Page: p5},
}, pdf.Rectangle{LLX: 54, LLY: 54, URX: 541, URY: 760},
    pdf.TOCOptions{Title: "Contents"})
