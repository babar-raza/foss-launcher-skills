var workbook = new Workbook();
var sheet = workbook.Worksheets[0];

for (var index = 0; index < 10; index++)
{
    sheet.Cells[index, 0].PutValue(index + 1);
}

var rules = sheet.ConditionalFormattings[sheet.ConditionalFormattings.Add()];
rules.AddArea(CellArea.CreateCellArea("A1", "A10"));
var rule = rules[rules.AddCondition(FormatConditionType.CellValue, OperatorType.Between, "3", "7")];
rule.Style.Pattern = FillPattern.Solid;
rule.Style.ForegroundColor = Color.FromArgb(255, 255, 199, 206);

workbook.Save("conditional-formatting-sample.xlsx");
