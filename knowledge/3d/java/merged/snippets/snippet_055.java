@Test
    public void testStlSaveOptions() {
        StlSaveOptions options = new StlSaveOptions();
        assertNotNull(options);
        
        options.setFlipCoordinateSystem(true);
        assertTrue(options.getFlipCoordinateSystem());
        
        // Note: getContentType/setContentType don't exist in On-Premise
        // Content type is determined by FileFormat during save/load
    }