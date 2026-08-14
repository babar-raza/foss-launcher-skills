var workbook = new Workbook();
var sheet = workbook.Worksheets[0];
sheet.Name = "Charts";

for (var month = 1; month <= 12; month++)
{
    sheet.Cells[month, 0].PutValue("Month " + month);
    sheet.Cells[month, 1].PutValue(month * 1000);
}

var chartIndex = sheet.Charts.Add(ChartType.Column, "Charts!$B$1:$B$13", 0, 4, 18, 8);
var chart = sheet.Charts[chartIndex];

workbook.Save("charts-sample.xlsx");
