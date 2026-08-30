async function testNumberValidation() {
  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", 10);
  worksheet.putValue("A2", 20);
  worksheet.putValue("A3", 30);

  const validation = new DataValidation();
  validation.type = "whole";
  validation.operator = "between";
  validation.formula1 = "1";
  validation.formula2 = "100";
  worksheet.addDataValidation(validation, "B1:B5");

  await workbook.save("outputfiles/test_number_validation.xlsx");
  console.log("Saved to outputfiles/test_number_validation.xlsx");
}