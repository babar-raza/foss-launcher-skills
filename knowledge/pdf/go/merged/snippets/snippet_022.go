func main() {
	path := "result_files/acroform_build.pdf"
	if len(os.Args) > 1 {
		path = os.Args[1]
	}

	doc, err := pdf.Open(path)
	if err != nil {
		log.Fatalf("open %s: %v", path, err)
	}
	form := doc.Form()

	fields := form.Fields()
	dumps := make([]fieldDump, 0, len(fields))
	for _, f := range fields {
		dumps = append(dumps, dumpField(f))
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(map[string]any{
		"source":          path,
		"needAppearances": form.NeedAppearances(),
		"fieldCount":      len(fields),
		"fields":          dumps,
	}); err != nil {
		log.Fatalf("encode: %v", err)
	}
}