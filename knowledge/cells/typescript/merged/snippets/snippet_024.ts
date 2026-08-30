async function testWorksheetManagement() {
  console.log("Testing worksheet management...");

  const workbook = new Workbook();

  const ws1 = workbook.worksheets.addWorksheet();
  console.log("Created worksheet:", ws1.name);

  const ws2 = workbook.worksheets.addWorksheet("CustomSheet1");
  console.log("Created worksheet:", ws2.name);

  console.log("Total worksheets:", workbook.worksheets.length);

  workbook.worksheets.removeWorksheet(1);
  console.log("After delete:", workbook.worksheets.length);

  const wsMain = workbook.worksheets.addWorksheet("MainSheet");
  wsMain.putValue("A1", "Main Worksheet");
  wsMain.putValue("A2", "This is the primary worksheet");

  const wsData = workbook.worksheets.addWorksheet("DataSheet");
  wsData.putValue("A1", "Data Worksheet");
  wsData.putValue("A2", "Contains data tables");

  const wsReport = workbook.worksheets.addWorksheet("ReportSheet");
  wsReport.putValue("A1", "Report Worksheet");
  wsReport.putValue("A2", "Contains reports");

  console.log(
    "Worksheets:",
    workbook.worksheets.worksheets.map((w) => w.name),
  );

  await workbook.save("outputfiles/test_worksheet_management.xlsx");
  console.log("Saved to outputfiles/test_worksheet_management.xlsx");

  const loaded = await Workbook.load(
    "outputfiles/test_worksheet_management.xlsx",
  );
  console.log(
    "Loaded worksheets:",
    loaded.worksheets.worksheets.map((w) => w.name),
  );
}