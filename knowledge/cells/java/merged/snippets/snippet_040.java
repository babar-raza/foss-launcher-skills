@Test
    void AF_51_setTopEnablesTop10Filter() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterTop10 top10 =
                    ws.getAutoFilter().getFilterColumns().get(0).getTop10();
            top10.setTop(true);
            assertTrue(top10.isEnabled());
            assertTrue(top10.isTop());
        }
    }