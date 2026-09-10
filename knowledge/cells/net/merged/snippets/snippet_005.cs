var workbook = new Workbook();
var sheet = workbook.Worksheets[0];

sheet.Cells["A1"].PutValue("Open");

var listValidationIndex = sheet.Validations.Add(CellArea.CreateCellArea("A1", "A3"));
var listValidation = sheet.Validations[listValidationIndex];
listValidation.Type = ValidationType.List;
listValidation.Formula1 = "\"Open,Closed\"";
listValidation.InCellDropDown = true;
listValidation.ShowError = true;
listValidation.ErrorTitle = "Invalid";
listValidation.ErrorMessage = "Choose from the list";

workbook.Save("validations-sample.xlsx");
