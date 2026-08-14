func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: ai_chat <input.pdf>")
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
	chat := ai.NewChatCopilot(client, ai.ChatOptions{Document: doc})

	fmt.Println("Ask about the document (blank line to quit):")
	in := bufio.NewScanner(os.Stdin)
	for {
		fmt.Print("\n> ")
		if !in.Scan() {
			break
		}
		q := strings.TrimSpace(in.Text())
		if q == "" {
			break
		}
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		answer, err := chat.Ask(ctx, q)
		cancel()
		if err != nil {
			fmt.Fprintln(os.Stderr, "ask:", err)
			continue
		}
		fmt.Println(answer)
	}
}