async function testMarkdownExport() {
  console.log("Testing Markdown export...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", "Name");
  worksheet.putValue("B1", "Age");
  worksheet.putValue("A2", "Alice");
  worksheet.putValue("B2", 25);
  worksheet.putValue("A3", "Bob");
  worksheet.putValue("B3", 30);

  const markdown = workbook.toMarkdown();
  console.log("Markdown:\n", markdown);

  await workbook.save("outputfiles/test_markdown_export.md");
  console.log("Saved to outputfiles/test_markdown_export.md");
}