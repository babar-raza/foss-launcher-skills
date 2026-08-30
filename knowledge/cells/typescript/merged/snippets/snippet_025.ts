async function testWorksheetRename() {
  const workbook = new Workbook();

  workbook.worksheets[0]!.name = "RenamedSheet";
  console.log("Renamed to:", workbook.worksheets[0]!.name);

  await workbook.save("outputfiles/test_worksheet_rename.xlsx");
  console.log("Saved to outputfiles/test_worksheet_rename.xlsx");
}