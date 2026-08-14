@Test
    void workbookDate1904SettingRoundTrips() {
        Workbook workbook = new Workbook();
        assertFalse(workbook.getSettings().getDate1904());
        workbook.getSettings().setDate1904(true);
        assertTrue(workbook.getSettings().getDate1904());
        workbook.getSettings().setDate1904(false);
        assertFalse(workbook.getSettings().getDate1904());
    }