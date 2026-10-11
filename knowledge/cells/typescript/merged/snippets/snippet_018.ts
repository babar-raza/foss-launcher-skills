async function testCellProtection() {
  console.log("Testing cell protection...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  const style = new Style();
  style.setLocked(true);
  style.setHidden(false);

  const cell = worksheet.getCell2("A1");
  cell.putValue("Protected Cell");
  cell.setStyle(style);

  worksheet.putValue("A2", "Unprotected Cell");

  await workbook.save("outputfiles/test_cell_protection.xlsx");
  console.log("Saved to outputfiles/test_cell_protection.xlsx");
}