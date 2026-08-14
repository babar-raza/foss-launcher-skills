@Test
    void worksheetViewMembersFollowSupportedPatterns() {
        Workbook workbook = new Workbook();
        Worksheet sheet = workbook.getWorksheets().get(0);

        sheet.setTabColor(Color.fromArgb(255, 34, 68, 102));
        sheet.setShowGridlines(false);
        sheet.setShowRowColumnHeaders(false);
        sheet.setShowZeros(false);
        sheet.setRightToLeft(true);
        sheet.setZoom(85);

        assertEquals(Color.fromArgb(255, 34, 68, 102), sheet.getTabColor());
        assertFalse(sheet.getShowGridlines());
        assertFalse(sheet.getShowRowColumnHeaders());
        assertFalse(sheet.getShowZeros());
        assertTrue(sheet.getRightToLeft());
        assertEquals(85, sheet.getZoom());
    }