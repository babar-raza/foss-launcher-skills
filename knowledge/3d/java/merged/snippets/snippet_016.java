@Test
    public void testGltfSaveOptions() {
        // GltfSaveOptions might not have no-arg constructor in On-Premise
        // Need to use FileFormat or FileContentType constructor
        GltfSaveOptions options = new GltfSaveOptions(FileFormat.GLTF2);
        assertNotNull(options);
        
        // Test new property names
        options.setPrettyPrint(true);
        assertTrue(options.getPrettyPrint());
        
        // BufferFile is the new property name (not BufferFilePrefix)
        options.setBufferFile("buffer_");
        assertEquals("buffer_", options.getBufferFile());
        
        // SaveExtras is now a boolean, not a String
        options.setSaveExtras(true);
        assertTrue(options.getSaveExtras());
    }