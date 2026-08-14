@Test
    void worksheetSettingsScenarioInMemory() {
        Workbook workbook = WorksheetScenarioFactory.createWorksheetSettingsWorkbook();
        WorksheetScenarioFactory.assertWorksheetSettings(workbook);
        WorksheetScenarioFactory.assertWorksheetSettingsScenarioHasVisibleSheet(workbook);
    }