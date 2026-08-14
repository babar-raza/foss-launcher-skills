import { Workbook } from "./aspose_cells";

const workbook = await Workbook.load("input.xlsx");
const sheet = workbook.worksheets.get(0)!;

const cell = sheet.getCell2("A1");
cell.putValue("Updated");

console.log("Loaded value:", sheet.getCell(0, 0)?.value);

await workbook.save("updated.xlsx");
