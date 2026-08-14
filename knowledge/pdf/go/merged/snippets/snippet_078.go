doc, err := pdf.Open("input.pdf")

// Remove pages in place (1-based). Numbers are de-duplicated and validated
// before anything is removed, so on error the document is unchanged.
err = doc.DeletePages(1, 3) // drop the first and third pages
err = doc.DeletePage(2)     // convenience for a single page

doc.Save("output.pdf")
