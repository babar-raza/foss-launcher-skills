@Test
    void CV_50_to_CV_59_integrationAllCellTypes() throws Exception {
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("cell-values.xlsx");
            LocalDateTime dt = LocalDateTime.of(2024, 3, 15, 10, 30, 0);

            try (Workbook wb = new Workbook()) {
                Cells cells = wb.getWorksheets().get(0).getCells();
                cells.get("A1").putValue("Hello");          // CV-50 String
                cells.get("A2").putValue(42);               // CV-51 Integer
                cells.get("A3").putValue(3.14);             // CV-52 Double
                cells.get("A4").putValue(true);             // CV-53 Boolean true
                cells.get("A5").putValue(false);            // CV-54 Boolean false
                cells.get("A6").putValue(dt);               // CV-55 DateTime
                cells.get("A7").setFormula("=A2*2");        // CV-56 Formula
                // A8 never written                         // CV-57 Blank
                cells.get("A9").putValue(1_000_000);        // CV-58 Large integer
                cells.get("A10").putValue(-0.001);          // CV-59 Negative double
                wb.save(path);
            }

            // --- API verification ---
            Workbook loaded = new Workbook(path);
            Cells cells = loaded.getWorksheets().get(0).getCells();

            // CV-50
            assertEquals("Hello", cells.get("A1").getValue());
            assertEquals(CellValueType.STRING, cells.get("A1").getType());

            // CV-51
            assertEquals(CellValueType.NUMBER, cells.get("A2").getType());
            // Value should be 42 (stored as int or double, check numeric equality)
            assertEquals(42.0, ((Number) cells.get("A2").getValue()).doubleValue(), 1e-9);

            // CV-52
            assertEquals(3.14, ((Number) cells.get("A3").getValue()).doubleValue(), 1e-9);

            // CV-53
            assertEquals(CellValueType.BOOLEAN, cells.get("A4").getType());
            assertEquals(true, cells.get("A4").getValue());

            // CV-54
            assertEquals(false, cells.get("A5").getValue());

            // CV-55
            assertEquals(CellValueType.DATE_TIME, cells.get("A6").getType());
            LocalDateTime loaded_dt = (LocalDateTime) cells.get("A6").getValue();
            assertEquals(dt.getYear(), loaded_dt.getYear());
            assertEquals(dt.getMonth(), loaded_dt.getMonth());
            assertEquals(dt.getDayOfMonth(), loaded_dt.getDayOfMonth());

            // CV-56
            assertEquals("=A2*2", cells.get("A7").getFormula());
            assertEquals(CellValueType.FORMULA, cells.get("A7").getType());

            // CV-57 Blank
            assertEquals(CellValueType.BLANK, cells.get("A8").getType());

            // CV-58
            assertEquals(1000000.0, ((Number) cells.get("A9").getValue()).doubleValue(), 1e-9);

            // CV-59
            assertEquals(-0.001, ((Number) cells.get("A10").getValue()).doubleValue(), 1e-12);

            // --- POI verification ---
            try (org.apache.poi.ss.usermodel.Workbook poiWb = WorkbookFactory.create(new File(path))) {
                org.apache.poi.ss.usermodel.Sheet poiSheet = poiWb.getSheetAt(0);

                // CV-50: String
                org.apache.poi.ss.usermodel.Row row0 = poiSheet.getRow(0);
                assertEquals(org.apache.poi.ss.usermodel.CellType.STRING, row0.getCell(0).getCellType());
                assertEquals("Hello", row0.getCell(0).getStringCellValue());

                // CV-51: Integer
                org.apache.poi.ss.usermodel.Row row1 = poiSheet.getRow(1);
                assertEquals(org.apache.poi.ss.usermodel.CellType.NUMERIC, row1.getCell(0).getCellType());
                assertEquals(42, (int) row1.getCell(0).getNumericCellValue());

                // CV-52: Double
                org.apache.poi.ss.usermodel.Row row2 = poiSheet.getRow(2);
                assertEquals(3.14, row2.getCell(0).getNumericCellValue(), 1e-9);

                // CV-53: Boolean true
                org.apache.poi.ss.usermodel.Row row3 = poiSheet.getRow(3);
                assertEquals(org.apache.poi.ss.usermodel.CellType.BOOLEAN, row3.getCell(0).getCellType());
                assertTrue(row3.getCell(0).getBooleanCellValue());

                // CV-54: Boolean false
                org.apache.poi.ss.usermodel.Row row4 = poiSheet.getRow(4);
                assertFalse(row4.getCell(0).getBooleanCellValue());

                // CV-55: DateTime
                org.apache.poi.ss.usermodel.Row row5 = poiSheet.getRow(5);
                org.apache.poi.ss.usermodel.Cell dateCell = row5.getCell(0);
                assertTrue(DateUtil.isCellDateFormatted(dateCell), "Date cell should be formatted as date");
                Date javaDate = DateUtil.getJavaDate(da