async function testDataValidation() {
  console.log("Testing data validation...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", "Option 1");
  worksheet.putValue("A2", "Option 2");
  worksheet.putValue("A3", "Option 3");

  const validation = new DataValidation();
  validation.type = "list";
  validation.formula1 = '"Option1,Option2,Option3"';
  worksheet.addDataValidation(validation, "B1:B10");

  await workbook.save("outputfiles/test_data_validation.xlsx");
  console.log("Saved to outputfiles/test_data_validation.xlsx");
}