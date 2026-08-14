async function testAutoFilter() {
  console.log("Testing auto filter...");

  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  worksheet.putValue("A1", "Name");
  worksheet.putValue("B1", "Age");
  worksheet.putValue("C1", "City");

  worksheet.putValue("A2", "Alice");
  worksheet.putValue("B2", "25");
  worksheet.putValue("C2", "New York");

  worksheet.putValue("A3", "Bob");
  worksheet.putValue("B3", "30");
  worksheet.putValue("C3", "London");

  worksheet.putValue("A4", "Charlie");
  worksheet.putValue("B4", "35");
  worksheet.putValue("C4", "Paris");

  worksheet.setAutoFilter("A1:C4");

  await workbook.save("outputfiles/test_auto_filter.xlsx");
  console.log("Saved to outputfiles/test_auto_filter.xlsx");
}