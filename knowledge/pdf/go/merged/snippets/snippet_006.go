func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: ai_summary <input.pdf>")
		os.Exit(2)
	}
	model := os.Getenv("AI_MODEL")
	if model == "" {
		fmt.Fprintln(os.Stderr, "AI_MODEL is required (e.g. gpt-4o-mini)")
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
	copilot := ai.NewSummaryCopilot(client, ai.SummaryOptions{
		Document: doc,
		MaxWords: 200,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	summary, err := copilot.GetSummary(ctx)
	if err != nil {
		fmt.Fprintln(os.Stderr, "summarize:", err)
		os.Exit(1)
	}
	fmt.Println(summary)

	out := filepath.Join("result_files", strings.TrimSuffix(filepath.Base(os.Args[1]), filepath.Ext(os.Args[1]))+"_summary.pdf")
	_ = os.MkdirAll("result_files", 0o755)
	if err := copilot.SaveSummary(ctx, out); err != nil {
		fmt.Fprintln(os.Stderr, "save summary pdf:", err)
		os.Exit(1)
	}
	fmt.Println("\nSaved:", out)
}