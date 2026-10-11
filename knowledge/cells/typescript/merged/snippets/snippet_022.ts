async function testBorderSettings() {
  console.log("Testing border settings...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;
  const style = new Style();

  style.getBorder().left = { style: "thick", color: "FF0000" };
  style.getBorder().right = { style: "thick", color: "FF0000" };
  style.getBorder().top = { style: "thick", color: "FF0000" };
  style.getBorder().bottom = { style: "thick", color: "FF0000" };

  const cell = worksheet.getCell2("A1");
  cell.putValue("Bordered Cell");
  cell.setStyle(style);

  await workbook.save("outputfiles/test_border_settings.xlsx");
  console.log("Saved to outputfiles/test_border_settings.xlsx");
}