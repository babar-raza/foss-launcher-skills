var workbook = new Workbook("input.xlsx");

workbook.Save("output.pdf", new PdfSaveOptions
{
    AllColumnsInOnePagePerSheet = true
});
