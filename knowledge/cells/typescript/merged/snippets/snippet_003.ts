import { Workbook } from "./aspose_cells";

const workbook = await Workbook.load("input.xlsx");
await workbook.save("output.html", { saveFormat: undefined });
