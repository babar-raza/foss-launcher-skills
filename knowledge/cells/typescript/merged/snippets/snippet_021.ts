async function testFillSettings() {
  console.log("Testing fill settings...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;
  const style = new Style();

  style.setForegroundColor("FFFF00");
  style.setBackgroundColor("FF0000");

  const cell = worksheet.getCell2("A1");
  cell.putValue("Colored Cell");
  cell.setStyle(style);

  await workbook.save("outputfiles/test_fill_settings.xlsx");
  console.log("Saved to outputfiles/test_fill_settings.xlsx");
}