doc, _ := pdf.Open("input.pdf")
page, _ := doc.Page(1)

// Add a hyperlink
link := pdf.NewLinkAnnotation(page, pdf.Rectangle{LLX: 50, LLY: 700, URX: 200, URY: 720})
link.SetAction(pdf.NewGoToURIAction("https://example.com"))
link.SetColor(&pdf.Color{R: 0, G: 0, B: 1, A: 1})
link.SetHighlight(pdf.LinkHighlightOutline) // /H click feedback: None / Invert (default) / Outline / Push
page.Annotations().Add(link)

// Highlight a passage
hl := pdf.NewHighlightAnnotation(page, pdf.Rectangle{LLX: 50, LLY: 600, URX: 300, URY: 615})
hl.SetColor(&pdf.Color{R: 1, G: 1, B: 0, A: 1})
hl.SetTitle("Reviewer")
hl.SetContents("Important paragraph")
hl.SetQuadPoints([]pdf.QuadPoint{
    {X1: 50, Y1: 615, X2: 300, Y2: 615, X3: 50, Y3: 600, X4: 300, Y4: 600},
})
page.Annotations().Add(hl)

// Iterate and filter
for _, a := range page.Annotations().All() {
    if a.AnnotationType() != pdf.AnnotationTypeLink {
        continue
    }
    if uri, ok := a.(*pdf.LinkAnnotation).Action().(*pdf.GoToURIAction); ok {
        fmt.Println(uri.URI())
    }
}

// Wire a form push button to a server submit
submit := pdf.NewLinkAnnotation(page, pdf.Rectangle{LLX: 50, LLY: 50, URX: 200, URY: 80})
submit.SetAction(pdf.NewSubmitFormAction(
    "https://example.com/api/subscribe",
    []string{"name", "email"},
    pdf.SubmitGetMethod|pdf.SubmitExportFormat,
))
page.Annotations().Add(submit)

doc.Save("with_annotations.pdf")
