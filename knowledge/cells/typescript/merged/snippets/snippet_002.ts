async function testAutoFilterWithData() {
  const workbook = new Workbook();
  const worksheet = workbook.worksheets[0]!;

  for (let i = 0; i < 10; i++) {
    worksheet.putValue(`A${i + 1}`, `Item ${i + 1}`);
    worksheet.putValue(`B${i + 1}`, Math.floor(Math.random() * 100));
    worksheet.putValue(`C${i + 1}`, ["Red", "Green", "Blue"][i % 3]);
  }

  worksheet.setAutoFilter("A1:C10");

  await workbook.save("outputfiles/test_auto_filter_data.xlsx");
  console.log("Saved to outputfiles/test_auto_filter_data.xlsx");
}