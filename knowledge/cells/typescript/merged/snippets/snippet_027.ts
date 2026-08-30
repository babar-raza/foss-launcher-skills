async function testWorksheetAccess() {
  const workbook = new Workbook();

  workbook.worksheets.addWorksheet("FirstSheet");
  workbook.worksheets.addWorksheet("SecondSheet");
  workbook.worksheets.addWorksheet("ThirdSheet");

  console.log("Worksheet 0:", workbook.worksheets[0]?.name);
  console.log("Worksheet 1:", workbook.worksheets[1]?.name);
  console.log("Worksheet 2:", workbook.worksheets[2]?.name);

  await workbook.save("outputfiles/test_worksheet_access.xlsx");
}