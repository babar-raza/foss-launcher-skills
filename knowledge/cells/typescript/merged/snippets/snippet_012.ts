async function testhtmlImport() {
  console.log("Testing html import...");

  const workbook = await Workbook.load("outputfiles/test_html_export.html");
  const worksheet = workbook.worksheets[0]!;

  console.log("A1:", worksheet.getCell(0, 0)?.value);
  console.log("B1:", worksheet.getCell(0, 1)?.value);
  console.log("A2:", worksheet.getCell(1, 0)?.value);
}