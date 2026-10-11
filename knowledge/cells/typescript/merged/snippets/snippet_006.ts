async function testCellValues() {
  console.log("Testing cell values...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  const intValues = [0, 1, -1, 42, 1000, -999];
  for (let i = 0; i < intValues.length; i++) {
    worksheet.putValue(`A${i + 1}`, intValues[i]);
  }

  const doubleValues = [0.0, 1.5, -2.7, 3.14159, 0.0001, -999.999];
  for (let i = 0; i < doubleValues.length; i++) {
    worksheet.putValue(`B${i + 1}`, doubleValues[i]);
  }

  const stringValues = [
    "Hello World",
    "Test String",
    "123",
    "3.14",
    "",
    "Special chars: !@#$%^&*()",
    "Unicode: 你好世界",
    "Multi\nline\nstring",
  ];
  for (let i = 0; i < stringValues.length; i++) {
    worksheet.putValue(`C${i + 1}`, stringValues[i]);
  }

  const formulas = [
    "=SUM(A1:A5)",
    "=A1+B1",
    '=IF(A1>0,"Positive","Non-positive")',
    "=VLOOKUP(A1,B1:C10,2,FALSE)",
    "=AVERAGE(A1:A10)",
    "=MAX(A1:A5)",
    "=MIN(A1:A5)",
    "=COUNT(A1:A10)",
  ];
  for (let i = 0; i < formulas.length; i++) {
    const cell = worksheet.getCell2(`D${i + 1}`);
    cell.setFormula(formulas[i]);
  }

  worksheet.putValue("A1", 42);
  worksheet.putValue("A2", 3.14159);
  worksheet.putValue("A3", "Hello");
  const cellA4 = worksheet.getCell2("A4");
  cellA4.setFormula("=SUM(A1:A2)");

  console.log("A1:", worksheet.getCell(0, 0)?.value);
  console.log("A2:", worksheet.getCell(1, 0)?.value);
  console.log("A3:", worksheet.getCell(2, 0)?.value);
  console.log("A4 formula:", worksheet.getCell(3, 0)?.formula);

  await workbook.save("outputfiles/test_cell_values.xlsx");
  console.log("Saved to outputfiles/test_cell_values.xlsx");
}