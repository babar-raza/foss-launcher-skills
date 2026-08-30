async function testWorkbookProtection() {
  console.log("Testing workbook protection...");

  const workbook = new Workbook();
  workbook.protect(true, "password");

  await workbook.save("outputfiles/test_workbook_protection.xlsx");
  console.log("Saved to outputfiles/test_workbook_protection.xlsx");
}