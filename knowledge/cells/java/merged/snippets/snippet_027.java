@Test
    void AF_24_blankFilterValueAccepted() throws Exception {
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.FilterValueCollection fv =
                    ws.getAutoFilter().getFilterColumns().get(0).getFilters();
            // Empty string is a valid filter value (matches blank cells in Excel)
            assertDoesNotThrow(() -> fv.add(""));
            assertEquals(1, fv.getCount());
        }
    }