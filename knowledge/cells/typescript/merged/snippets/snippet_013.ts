async function testJsonExport() {
  console.log("Testing JSON export...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", "Name");
  worksheet.putValue("B1", "Age");
  worksheet.putValue("A2", "Alice");
  worksheet.putValue("B2", 25);
  worksheet.putValue("A3", "Bob");
  worksheet.putValue("B3", 30);

  const json = workbook.toJson();
  console.log("JSON:", json);

  await workbook.save("outputfiles/test_json_export.json");
  console.log("Saved to outputfiles/test_json_export.json");
}