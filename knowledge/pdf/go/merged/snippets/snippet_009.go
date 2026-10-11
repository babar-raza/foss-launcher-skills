func main() {
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		log.Fatalf("mkdir: %v", err)
	}

	// --- Document scaffolding ---------------------------------------
	// 8 portrait A4 pages up front: cover, TOC, then 6 body sections
	// (text, image, form, annotations, redaction, restaurant bill).
	// Sales report, landscape chart, and vector showcase are appended
	// later so they land *after* any sales-report continuation pages.
	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	for i := 0; i < 7; i++ {
		mustAddPage(doc.AddBlankPageFromFormat(pdf.PageFormatA4))
	}

	coverPage, _ := doc.Page(1)
	tocPage, _ := doc.Page(2)
	textPage, _ := doc.Page(3)
	imagePage, _ := doc.Page(4)
	formPage, _ := doc.Page(5)
	annotPage, _ := doc.Page(6)
	redactPage, _ := doc.Page(7)
	billPage, _ := doc.Page(8)

	// --- Body content -----------------------------------------------
	addCoverPage(doc, coverPage)
	// TOC is filled last — once every section is anchored we know
	// the destination names exist.
	addPageText(doc, textPage)
	addPageImage(imagePage)
	addFormFields(doc, formPage)
	addAnnotations(annotPage)
	addRedactionDemo(doc, redactPage)
	addRestaurantBill(billPage)

	// Sales report — append a fresh page, then let the table grow.
	mustAddPage(doc.AddBlankPageFromFormat(pdf.PageFormatA4))
	salesPage, _ := doc.Page(doc.PageCount())
	addSalesReport(doc, salesPage)

	// Landscape wide chart — physically wider page via Landscape().
	mustAddPage(doc.AddBlankPage(pdf.PageFormatA4.Landscape().Width, pdf.PageFormatA4.Landscape().Height))
	landscapePage, _ := doc.Page(doc.PageCount())
	addLandscapeChart(landscapePage)

	// Vector graphics showcase.
	mustAddPage(doc.AddBlankPageFromFormat(pdf.PageFormatA4))
	vectorPage, _ := doc.Page(doc.PageCount())
	addVectorShowcase(doc, vectorPage)

	// Flattening showcase — last content page. Builds interactive fields and
	// an annotation, then bakes them into static content via Flatten().
	mustAddPage(doc.AddBlankPageFromFormat(pdf.PageFormatA4))
	flattenPage, _ := doc.Page(doc.PageCount())
	addFlattenDemo(doc, flattenPage)

	// Flow Layout & Floats — "Giants of Physics", a two-column tribute laid out
	// entirely by the document-generator flow engine (NewFlow): a portrait,
	// heading, prose, a formula card and a pull-quote per column, split with a
	// column break. The flow appends its own page(s) at the end, so capture the
	// first one for the TOC/outline anchor.
	flowStartCount := doc.PageCount()
	addFlowShowcase(doc)
	flowPage, _ := doc.Page(flowStartCount + 1)

	// Document Conversion — a meta page filled after the furniture pass so
	// its thumbnail shows the finished Restaurant Bill page (see
	// addConversionShowcase below).
	mustAddPage(doc.AddBlankPageFromFormat(pdf.PageFormatA4))
	convertPage, _ := doc.Page(doc.PageCount())

	// Page Rendering — a meta page whose thumbnails are renders of other pages
	// of this very document, produced by the pure-Go renderer. Its content is
	// filled in below, after the per-page furniture so the thumbnails show the
	// finished pages (logo, footer, watermark and all).
	mustAddPage(doc.AddBlankPageFromFormat(pdf.PageFormatA4))
	renderPage, _ := doc.Page(doc.PageCount())

	// --- Named destinations -----------------------------------------
	// The TOC links and the outline both target these. Forward
	// references through NewNamedDestination work because the named
	// destination resolves at view time (and writers serialise
	// /Catalog/Names/Dests at the end).
	sections := []section{
		{destText, "Text Capabilities Showcase", "text", textPage},
		{destImage, "Image Embedding", "image", imagePage},
		{destForm, "AcroForm Fields", "form", formPage},
		{destAnnot, "Annotation Gallery", "annotations", annotPage},
		{destRedact, "Redactions", "redaction", redactPage},
		{destBill, "Restaurant Bill", "bill", billPage},
		{destSales, "Multi-Page Sales Report", "sales", salesPage},
		{destLandscape, "Annual Sales — 12 Month Trend", "landscape", landscapePage},
		{destVector, "Vector Graphics", "vector", vectorPage},
		{destFlatten, "Form & Annotation Flattening", "flatten", flattenPage},
		{destFlow, "Flow Layout — Giants of Physics", "flow", flowPage},
		{destConvert, "Document Conversion", "convert", convertPage},
		{destRender, "Rendering & Imposition", "image", renderPage},
	}
	named := doc.NamedDestinations()
	for _, s := range sections {
		if err := named.Add(s.dest, pdf.NewDestinationFit(s.page)); err != nil {
			log.Fatalf("named dest %q: %v", s.dest, err)
		}
	}

	// --- Table of Contents (depends on named destinations) ----------
	addTOC(doc, tocPage, sections)

	// Note: ApplyRedactions is called inside addRedactionDemo so it can
	// run on a SUBSET of that page's /Redact annotations — the demo
	// preserves two annots in mark-mode by adding them after the call.

	// --- Per-page furniture: footer, logo 