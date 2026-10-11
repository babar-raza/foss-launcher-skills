private static void generateShapeXlsx(Path cp, Path src) throws IOException {
        Workbook wb = new Workbook();
        wb.getWorksheets().get(0).getShapes().add(0, 0, 5, 5, AutoShapeType.RECTANGLE);
        saveWorkbook(wb, cp.resolve("shape.xlsx")); saveWorkbook(wb, src.resolve("shape.xlsx"));
    }