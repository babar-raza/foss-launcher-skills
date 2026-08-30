async function testMixedValues() {
  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", 42);
  worksheet.putValue("A2", 3.14159);
  worksheet.putValue("A3", "Hello World");
  const cellA4 = worksheet.getCell2("A4");
  cellA4.setFormula("=SUM(A1:A2)");
  worksheet.putValue("A5", -100);
  worksheet.putValue("A6", 2.71828);
  worksheet.putValue("A7", "");
  const cellA8 = worksheet.getCell2("A8");
  cellA8.setFormula("=A1+A2");
  worksheet.putValue("A9", "Test String");
  worksheet.putValue("A10", 0);

  await workbook.save("outputfiles/test_mixed_values.xlsx");
  console.log("Saved to outputfiles/test_mixed_values.xlsx");

  const loaded = await Workbook.load("outputfiles/test_mixed_values.xlsx");
  const ws = loaded.worksheets[0]!;
  console.log("Loaded A1:", ws.getCell(0, 0)?.value);
  console.log("Loaded A3:", ws.getCell(2, 0)?.value);
  console.log("Loaded A4 formula:", ws.getCell(3, 0)?.formula);
}