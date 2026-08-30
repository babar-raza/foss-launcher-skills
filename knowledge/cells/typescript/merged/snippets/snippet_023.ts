async function testAlignment() {
  console.log("Testing alignment...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;
  const style = new Style();

  style.setHorizontalAlignment("center");
  style.setVerticalAlignment("center");
  style.setWrapText(true);

  const cell = worksheet.getCell2("A1");
  cell.putValue("Centered Text\nWith Wrap");
  cell.setStyle(style);

  worksheet.setColumnWidth(0, 20);
  worksheet.setRowHeight(0, 40);

  await workbook.save("outputfiles/test_alignment.xlsx");
  console.log("Saved to outputfiles/test_alignment.xlsx");
}