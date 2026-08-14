private static void generateTableXlsx(Path cp, Path src) throws IOException {
        XSSFWorkbook wb = new XSSFWorkbook();
        XSSFSheet sheet = wb.createSheet("Sheet1");
        org.apache.poi.ss.usermodel.Row hdr = sheet.createRow(0);
        hdr.createCell(0).setCellValue("Product");
        hdr.createCell(1).setCellValue("Region");
        hdr.createCell(2).setCellValue("Revenue");
        String[][] rows = {{"Apple","North","100"},{"Banana","South","200"},{"Cherry","East","300"}};
        for (int i = 0; i < rows.length; i++) {
            org.apache.poi.ss.usermodel.Row r = sheet.createRow(i + 1);
            r.createCell(0).setCellValue(rows[i][0]);
            r.createCell(1).setCellValue(rows[i][1]);
            r.createCell(2).setCellValue(Double.parseDouble(rows[i][2]));
        }
        AreaReference area = new AreaReference("A1:C4", SpreadsheetVersion.EXCEL2007);
        XSSFTable table = sheet.createTable(area);
        table.setName("Table5"); table.setDisplayName("Table5");
        org.openxmlformats.schemas.spreadsheetml.x2006.main.CTTableStyleInfo tsi = table.getCTTable().addNewTableStyleInfo();
        tsi.setName("TableStyleMedium2"); tsi.setShowFirstColumn(false); tsi.setShowLastColumn(false);
        tsi.setShowRowStripes(true); tsi.setShowColumnStripes(false);
        writePoi(wb, cp.resolve("table.xlsx")); writePoi(wb, src.resolve("table.xlsx")); wb.close();
    }