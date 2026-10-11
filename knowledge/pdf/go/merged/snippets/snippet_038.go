func main() {
	query := "Marketing"
	path := "testdata/marketing.pdf"
	if len(os.Args) > 1 {
		query = os.Args[1]
	}
	if len(os.Args) > 2 {
		path = os.Args[2]
	}

	doc, err := pdf.Open(path)
	if err != nil {
		log.Fatalf("open %q: %v", path, err)
	}

	// Case-insensitive so "Marketing" and "marketing" both surface.
	found, err := doc.SearchText(query, pdf.SearchOptions{CaseInsensitive: true})
	if err != nil {
		log.Fatalf("search %q: %v", query, err)
	}

	matches := make([]match, 0, len(found))
	for _, m := range found {
		matches = append(matches, match{
			Page: m.PageNumber,
			Text: m.Text,
			Rect: rect{round1(m.Rect.LLX), round1(m.Rect.LLY), round1(m.Rect.URX), round1(m.Rect.URY)},
		})
	}

	result := struct {
		File    string  `json:"file"`
		Query   string  `json:"query"`
		Count   int     `json:"count"`
		Matches []match `json:"matches"`
	}{File: path, Query: query, Count: len(matches), Matches: matches}

	out, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		log.Fatalf("marshal: %v", err)
	}
	fmt.Println(string(out))
}