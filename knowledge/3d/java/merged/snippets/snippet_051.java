@Test
    public void testStlAsciiExport() throws IOException {
        Scene scene = new Scene();
        Mesh mesh = new Mesh("TestMesh");
        
        mesh.addControlPoint(0, 0, 0);
        mesh.addControlPoint(1, 0, 0);
        mesh.addControlPoint(0, 1, 0);
        
        mesh.createPolygon(new int[]{0, 1, 2});
        
        scene.getRootNode().createChildNode("TestNode", mesh);
        
        Path outputPath = Files.createTempFile("test_export_ascii", ".stl");
        try {
            StlSaveOptions options = new StlSaveOptions();
            // Set the file format explicitly
            options.setFileFormat(FileFormat.STLASCII);
            scene.save(outputPath.toString(), options);
            
            assertTrue(Files.exists(outputPath));
            String content = Files.readString(outputPath);
            
            assertTrue(content.contains("solid"), "ASCII STL should start with 'solid'");
            assertTrue(content.contains("endsolid"), "ASCII STL should end with 'endsolid'");
            assertTrue(content.contains("facet normal"), "ASCII STL should contain facet data");
            assertTrue(content.contains("vertex"), "ASCII STL should contain vertex data");
        } finally {
            Files.deleteIfExists(outputPath);
        }
    }