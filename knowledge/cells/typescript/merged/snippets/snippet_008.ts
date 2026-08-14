function testhtmlExport() {
  console.log("Testing html export...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", "Name");
  worksheet.putValue("B1", "Age");
  worksheet.putValue("A2", "Alice");
  worksheet.putValue("B2", 25);
  worksheet.putValue("A3", "Bob");
  worksheet.putValue("B3", 30);

  workbook.save("outputfiles/test_html_export.html");
  console.log("Saved to outputfiles/test_html_export.html");
}