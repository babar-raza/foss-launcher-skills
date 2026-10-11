@Test
    void AF_12_duplicateColumnIndexThrows() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(1);
            assertThrows(CellsException.class,
                    () -> ws.getAutoFilter().getFilterColumns().add(1));
        }
    }