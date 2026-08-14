private static void generateCompareXlsx(Path cp, Path src) throws IOException {
        Workbook wb = new Workbook();
        wb.getWorksheets().get(0).getPictures().add(0, 0, 5, 5, JPEG_1X1);
        saveWorkbook(wb, cp.resolve("compare").resolve("17.6.3-ByCells.xlsx"));
        saveWorkbook(wb, src.resolve("compare").resolve("17.6.3-ByCells.xlsx"));
    }