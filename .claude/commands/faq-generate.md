# S-22: FAQ Generate — Knowledge-Based FAQ Creation

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}` — path to the content page to add FAQ to

## Purpose
Generate FAQ questions and answers grounded in the knowledge model. Can append a FAQ section to an existing content page or generate standalone FAQ content. Each answer must be traceable to verified claims.

## Pre-conditions
1. Content file must exist (the page to add FAQ to)
2. Knowledge model must exist: `knowledge/{family}/{platform}/merged/index.json`
3. Knowledge must not be stale

## Steps

1. **Read the content file** at $ARGUMENTS

2. **Identify product**: Extract `{family}` and `{platform}` from file path

3. **Load knowledge**:
   - `claims.json` — for factual answers
   - `api_surface.json` — for API usage questions
   - `formats.json` — for format support questions
   - `limitations.md` — for limitation-aware answers
   - `forbidden_claims` from index.json — to avoid forbidden assertions

4. **Analyze page topic**: Read the page content to understand what topic it covers:
   - Extract main headings and key terms
   - Identify the primary API classes/methods discussed
   - Note any formats or features mentioned

5. **Generate FAQ categories** (select relevant ones based on page topic):

   a. **API Usage** (2–4 questions):
      - "How do I {action} using {ClassName}?"
      - Based on methods in api_surface.json relevant to the page topic
      - Each answer must reference verified API

   b. **Format Support** (1–3 questions, if formats are relevant):
      - "Does {product} support {format} {import/export}?"
      - Answers sourced from formats.json
      - Include direction specifics (import, export, or both)

   c. **Limitations & Troubleshooting** (1–3 questions):
      - "Can I {action that has a limitation}?"
      - Source from limitations.md and forbidden_claims
      - Honest answers acknowledging what is NOT supported

   d. **Installation & Setup** (1–2 questions, if relevant):
      - "What are the prerequisites for {product}?"
      - Source from install.md in knowledge

6. **Deduplicate**: If the page already has a FAQ section:
   - Read existing questions
   - Skip any generated questions that overlap with existing ones
   - Only add genuinely new questions

7. **Format questions**: Use consistent format:
   ```markdown
   ### {Question}?

   {Answer paragraph grounded in claims.json}
   ```

8. **Append to page**: Add FAQ section (or append to existing one):
   - If no FAQ section exists, add `## Frequently Asked Questions` heading
   - Append generated Q&A pairs
   - Ensure each answer is factual and traceable

## Output

```
FAQ GENERATE — {content-file-path}
Product: {family}/{platform}

Questions generated: {count}
  API Usage:      {n}
  Format Support: {n}
  Limitations:    {n}
  Setup:          {n}

Deduplicated (skipped): {n}
Questions added: {count}
```

## Post-conditions
- After adding FAQ, the chain continues:
  1. S-23 (ground-check) — verify all FAQ answers are grounded
  2. S-24 (evidence-cite) — attach citations to FAQ answers

## Error handling
- If knowledge not found → abort
- If page already has comprehensive FAQ (>10 questions) → skip with message
- If no relevant claims for FAQ → add 0 questions with note
