doc, _ := pdf.Open("report.pdf")

// (Assume the document already has outline bookmarks — see Outlines above.)
// Generate a TOC from the bookmark tree and insert it at the front.
added, _ := doc.GenerateTOC(pdf.TOCOptions{Title: "Table of Contents"})
fmt.Println(added, "TOC page(s) added") // page numbers/links reflect the shift

doc.Save("with_toc.pdf")
