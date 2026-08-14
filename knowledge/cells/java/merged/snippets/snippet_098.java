@Test
    void worksheetProtectionMembersFollowSupportedPatterns() {
        Workbook workbook = new Workbook();
        Worksheet sheet = workbook.getWorksheets().get(0);

        sheet.protect();
        sheet.getProtection().setAllowEditingObject(false);
        sheet.getProtection().setAllowEditingScenario(false);
        sheet.getProtection().setAllowFiltering(false);
        sheet.getProtection().setAllowSelectingLockedCell(false);
        sheet.getProtection().setAllowSelectingUnlockedCell(false);

        assertTrue(sheet.getProtection().isProtected());
        assertFalse(sheet.getProtection().getAllowEditingObject());
        assertFalse(sheet.getProtection().getAllowEditingScenario());
        assertFalse(sheet.getProtection().getAllowFiltering());
        assertFalse(sheet.getProtection().getAllowSelectingLockedCell());
        assertFalse(sheet.getProtection().getAllowSelectingUnlockedCell());
    }