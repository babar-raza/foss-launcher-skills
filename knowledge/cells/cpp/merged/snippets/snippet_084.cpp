#include "aspose/cells_foss/Workbook.h"
#include "aspose/cells_foss/Worksheet.h"
#include "aspose/cells_foss/Cell.h"

using namespace Aspose::Cells_FOSS;

Workbook workbook("products.xlsx");
Worksheet& sheet = workbook.GetWorksheets()["Products"];

std::string name = sheet.GetCells()["A2"].GetStringValue();
double price = sheet.GetCells()["B2"].GetValue().AsDouble();
std::string total = sheet.GetCells()["B4"].GetDisplayStringValue();  // formatted formula result
