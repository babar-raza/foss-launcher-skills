var workbook = new Workbook();
var sheet = workbook.Worksheets[0];

sheet.Cells["A1"].PutValue("Product");
sheet.Cells["B1"].PutValue("Category");
sheet.Cells["C1"].PutValue("Price");
sheet.Cells["A2"].PutValue("Laptop");
sheet.Cells["B2"].PutValue("Electronics");
sheet.Cells["C2"].PutValue(999.99);
sheet.Cells["A3"].PutValue("Mouse");
sheet.Cells["B3"].PutValue("Electronics");
sheet.Cells["C3"].PutValue(29.99);

var tableIndex = sheet.ListObjects.Add("A1", "C3", true);
var table = sheet.ListObjects[tableIndex];
table.DisplayName = "Products";
table.TableStyleType = TableStyleType.TableStyleMedium2;
table.ShowTotals = true;

workbook.Save("products-table.xlsx");
