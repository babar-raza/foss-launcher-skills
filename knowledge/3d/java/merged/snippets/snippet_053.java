@Test
    public void testCreateSimpleStlAscii() throws IOException {
        Path testPath = Files.createTempFile("test_ascii", ".stl");
        try {
            String stlContent = "solid test\n" +
                               " facet normal 0 0 1\n" +
                               "  outer loop\n" +
                               "   vertex 0 0 0\n" +
                               "   vertex 1 0 0\n" +
                               "   vertex 0 1 0\n" +
                               "  endloop\n" +
                               " endfacet\n" +
                               "endsolid test\n";
            
            Files.writeString(testPath, stlContent);
            
            Scene scene = Scene.fromFile(testPath.toString(), new StlLoadOptions());
            assertNotNull(scene);
            
            Node rootNode = scene.getRootNode();
            assertNotNull(rootNode);
        } finally {
            Files.deleteIfExists(testPath);
        }
    }