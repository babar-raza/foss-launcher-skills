async function testHyperlinks() {
  console.log("Testing hyperlinks...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", "Click here");
  worksheet.getCell2("A1").setHyperlink("https://www.google.com");

  worksheet.putValue("A3", "Send email");
  worksheet.getCell2("A3").setHyperlink("mailto:test@example.com");

  worksheet.putValue("A5", "Internal link");
  worksheet.getCell2("A5").setHyperlink("#Sheet1!A1");

  await workbook.save("outputfiles/test_hyperlinks.xlsx");
  console.log("Saved to outputfiles/test_hyperlinks.xlsx");
}