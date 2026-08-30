async function testHtmlExport() {
  console.log("Testing HTML export...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", "Name");
  worksheet.putValue("B1", "Age");
  worksheet.putValue("C1", "City");
  worksheet.putValue("A2", "Alice");
  worksheet.putValue("B2", 25);
  worksheet.putValue("C2", "New York");
  worksheet.putValue("A3", "Bob");
  worksheet.putValue("B3", 30);
  worksheet.putValue("C3", "London");

  const html = worksheetToHtml(worksheet);
  console.log("HTML:\n", html);

  await workbook.save("outputfiles/test_html_export.xlsx");
  console.log("Saved to outputfiles/test_html_export.xlsx");
}