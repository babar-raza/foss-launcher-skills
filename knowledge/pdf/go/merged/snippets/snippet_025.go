func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: ai_make_searchable <scanned.pdf>")
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

	client := ai.NewOpenAIClient(ai.OpenAIClientOptions{
		BaseURL: os.Getenv("AI_BASE_URL"),
		APIKey:  os.Getenv("AI_API_KEY"),
		Model:   model,
	})
	engine := ai.NewLLMOCREngine(client, ai.LLMOCROptions{})
	copilot := ai.NewOcrCopilot(engine, ai.OcrOptions{Document: doc})

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()

	n, err := copilot.MakeSearchable(ctx)
	if err != nil {
		fmt.Fprintln(os.Stderr, "ocr:", err)
		os.Exit(1)
	}
	fmt.Printf("OCRed %d scanned page(s)\n", n)

	out := filepath.Join("result_files", strings.TrimSuffix(filepath.Base(os.Args[1]), filepath.Ext(os.Args[1]))+"_searchable.pdf")
	_ = os.MkdirAll("result_files", 0o755)
	if err := doc.Save(out); err != nil {
		fmt.Fprintln(os.Stderr, "save:", err)
		os.Exit(1)
	}
	fmt.Println("Saved:", out)
}