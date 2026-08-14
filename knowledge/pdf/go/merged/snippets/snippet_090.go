// Named destinations — define once, reuse from outlines and links
doc.NamedDestinations().Add("intro",    pdf.NewDestinationFit(page1))
doc.NamedDestinations().Add("appendix", pdf.NewDestinationFitH(page2, 500))

oic := pdf.NewOutlineItemCollection(doc)
oic.SetTitle("Appendix")
oic.SetDestination(pdf.NewNamedDestination(doc, "appendix"))
doc.Outlines().Add(oic)
