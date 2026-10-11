doc, _ := pdf.Open("input.pdf")
page, _ := doc.Page(1)

// Top-level bookmark with style + destination
chapter := pdf.NewOutlineItemCollection(doc)
chapter.SetTitle("Chapter 1")
chapter.SetBold(true)
chapter.SetColor(&pdf.Color{R: 0, G: 0, B: 0.8, A: 1})
chapter.SetDestination(pdf.NewDestinationXYZ(page, 0, 800, 1.0))
doc.Outlines().Add(chapter)

// Nested child
section := pdf.NewOutlineItemCollection(doc)
section.SetTitle("Section 1.1")
section.SetDestination(pdf.NewDestinationFit(page))
chapter.Add(section)

doc.Save("with_bookmarks.pdf")
