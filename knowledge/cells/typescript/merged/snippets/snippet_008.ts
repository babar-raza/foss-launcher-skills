async function testEdgeCases() {
  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  const cell1 = worksheet.getCell2("A1");
  console.log("None value:", cell1.value);

  worksheet.putValue("A2", "");
  console.log("Empty string:", worksheet.getCell(1, 0)?.value);

  worksheet.putValue("A3", 999999999999);
  console.log("Large number:", worksheet.getCell(2, 0)?.value);

  worksheet.putValue("A4", 0.0000001);
  console.log("Small decimal:", worksheet.getCell(3, 0)?.value);

  worksheet.putValue("A5", 1.23e-10);
  console.log("Scientific notation:", worksheet.getCell(4, 0)?.value);

  await workbook.save("outputfiles/test_edge_cases.xlsx");
  console.log("Saved to outputfiles/test_edge_cases.xlsx");
}