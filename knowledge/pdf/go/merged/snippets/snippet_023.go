func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: ai_alt_text <tagged.pdf>")
		os.Exit(2)
	}
	model := os.Getenv("AI_MODEL")
	if model == "" {
		fmt.Fprintln(os.Stderr, "AI_MODEL is required (a vision model, e.g. gpt-4o-mini)")
		os.Exit(2)
	}

	doc, err := pdf.Open(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, "open:", err)
		os.Exit(1)
	}

	before := doc.ValidatePDFUA()
	fmt.Printf("Before: %d figure(s) missing alt text\n", countRule(before, "UA_FIGURE_NO_ALT"))

	client := ai.NewOpenAIClient(ai.OpenAIClientOptions{
		BaseURL: os.Getenv("AI_BASE_URL"),
		APIKey:  os.Getenv("AI_API_KEY"),
		Model:   model,
	})
	cop := ai.NewImageDescriptionCopilot(client, ai.ImageDescriptionOptions{})

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	n, err := cop.FillAltTexts(ctx, doc)
	if err != nil {
		fmt.Fprintln(os.Stderr, "fill alt texts:", err)
		os.Exit(1)
	}
	fmt.Printf("Filled alt text on %d figure(s)\n", n)

	out := filepath.Join("result_files", strings.TrimSuffix(filepath.Base(os.Args[1]), filepath.Ext(os.Args[1]))+"_alt.pdf")
	_ = os.MkdirAll("result_files", 0o755)
	if err := doc.Save(out); err != nil {
		fmt.Fprintln(os.Stderr, "save:", err)
		os.Exit(1)
	}
	fmt.Println("Saved:", out)
}