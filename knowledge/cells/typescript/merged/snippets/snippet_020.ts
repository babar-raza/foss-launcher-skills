async function testFontSettings() {
  console.log("Testing font settings...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;
  const style = new Style();

  style.setFontName("Arial");
  style.setFontSize(14);
  style.setBold(true);
  style.setItalic(true);
  style.setFontColor("FF0000");

  const cell = worksheet.getCell2("A1");
  cell.putValue("Styled Text");
  cell.setStyle(style);

  await workbook.save("outputfiles/test_font_settings.xlsx");
  console.log("Saved to outputfiles/test_font_settings.xlsx");
}