async function testWorksheetCopy() {
  const workbook = new Workbook();

  const ws1 = workbook.worksheets[0]!;
  ws1.putValue("A1", "Original Data");
  ws1.putValue("A2", "Row 2");

  const ws2 = workbook.worksheets.addWorksheet("CopySheet");
  ws2.putValue("A1", "Copied Data");

  console.log(
    "Worksheets:",
    workbook.worksheets.worksheets.map((w) => w.name),
  );

  await workbook.save("outputfiles/test_worksheet_copy.xlsx");
  console.log("Saved to outputfiles/test_worksheet_copy.xlsx");
}