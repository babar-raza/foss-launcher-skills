func main() {
	src := "docs/feature_showcase.pdf"
	if len(os.Args) > 1 {
		src = os.Args[1]
	}
	dpi := 120.0
	if len(os.Args) > 2 {
		if v, err := strconv.ParseFloat(os.Args[2], 64); err == nil {
			dpi = v
		}
	}

	doc, err := pdf.Open(src)
	if err != nil {
		log.Fatalf("open %q: %v", src, err)
	}
	outDir := filepath.Join("result_files", "render")
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		log.Fatalf("mkdir: %v", err)
	}

	for i := 1; i <= doc.PageCount(); i++ {
		out := filepath.Join(outDir, fmt.Sprintf("page-%02d.png", i))
		renderOne(doc, i, dpi, out)
	}
	fmt.Printf("rendered %d page(s) at %.0f DPI → %s\n", doc.PageCount(), dpi, outDir)

	// The whole document as one multi-page TIFF.
	tiffPath := filepath.Join(outDir, "document.tiff")
	renderTIFF(doc, dpi, tiffPath)
}