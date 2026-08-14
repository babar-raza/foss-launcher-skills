@Test
    public void testStlBinaryExport() throws IOException {
        Scene scene = new Scene();
        Mesh mesh = new Mesh("TestMesh");
        
        mesh.addControlPoint(0, 0, 0);
        mesh.addControlPoint(1, 0, 0);
        mesh.addControlPoint(0, 1, 0);
        mesh.addControlPoint(0, 0, 1);
        
        mesh.createPolygon(new int[]{0, 1, 2});
        mesh.createPolygon(new int[]{0, 1, 3});
        mesh.createPolygon(new int[]{0, 2, 3});
        mesh.createPolygon(new int[]{1, 2, 3});
        
        scene.getRootNode().createChildNode("TestNode", mesh);
        
        Path outputPath = Files.createTempFile("test_export", ".stl");
        try {
            StlSaveOptions options = new StlSaveOptions();
            // Set the file format explicitly
            options.setFileFormat(FileFormat.STL_BINARY);
            scene.save(outputPath.toString(), options);
            
            assertTrue(Files.exists(outputPath));
            assertTrue(Files.size(outputPath) > 80, "STL binary file should be larger than header");
            
            byte[] content = Files.readAllBytes(outputPath);
            assertEquals(84 + (4 * 50), content.length, "Binary STL with 4 faces should be 284 bytes");
        } finally {
            Files.deleteIfExists(outputPath);
        }
    }