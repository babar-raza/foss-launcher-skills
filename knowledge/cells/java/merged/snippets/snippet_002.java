private static void generateAutofilterXlsx(Path cp, Path src) throws IOException {
        Workbook wb = new Workbook();
        Worksheet ws = wb.getWorksheets().get(0);
        ws.getCells().get("A1").putValue("Title");
        ws.getCells().get("A2").putValue("Name");
        ws.getCells().get("B2").putValue("Region");
        ws.getCells().get("C2").putValue("Score");
        ws.getCells().get("A3").putValue("Alice"); ws.getCells().get("B3").putValue("North"); ws.getCells().get("C3").putValue(90);
        ws.getCells().get("A4").putValue("Bob");   ws.getCells().get("B4").putValue("South"); ws.getCells().get("C4").putValue(80);
        ws.getAutoFilter().setRange("A2:C2");
        saveWorkbook(wb, cp.resolve("Autofilter.xlsx"));
        saveWorkbook(wb, src.resolve("Autofilter.xlsx"));
    }