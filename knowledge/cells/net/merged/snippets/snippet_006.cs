var workbook = new Workbook();
var sheet = workbook.Worksheets[0];

sheet.Cells["A1"].PutValue("Docs");
var link = sheet.Hyperlinks[sheet.Hyperlinks.Add("A1", 1, 1, "https://example.com/docs")];
link.TextToDisplay = "Docs";

var name = workbook.DefinedNames[workbook.DefinedNames.Add("GlobalRange", "='Sheet1'!$A$1:$D$5")];
name.Comment = "Primary sample range";

workbook.Save("hyperlinks-and-names-sample.xlsx");
