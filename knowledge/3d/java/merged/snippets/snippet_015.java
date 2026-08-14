@Test
    public void testGltfLoadOptions() {
        // GltfLoadOptions constructor takes no args in .NET FOSS but On-Premise might not have it
        // The API has changed, using no-arg constructor
        GltfLoadOptions options = new GltfLoadOptions();
        assertNotNull(options);
        
        // FlipTexCoordV is the new property name for flip texture coordinate V
        options.setFlipTexCoordV(true);
        assertTrue(options.getFlipTexCoordV());
    }