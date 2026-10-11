using Aspose.Cells_FOSS;

var workbook = new Workbook("report.xlsx");
var sheet = workbook.Worksheets[0];

sheet.PageSetup.PaperSize = PaperSizeType.PaperA4;
sheet.PageSetup.Orientation = PageOrientationType.Landscape;

workbook.Save("report.pdf", new PdfSaveOptions
{
    OnePagePerSheet = true
});
