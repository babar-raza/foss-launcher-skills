@Test
    public void testCreateSimpleStlBinary() throws IOException {
        Path testPath = Files.createTempFile("test_binary", ".stl");
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            byte[] header = new byte[80];
            byte[] countBytes = new byte[]{1, 0, 0, 0};
            byte[] faceData = new byte[50];
            
            baos.write(header);
            baos.write(countBytes);
            baos.write(faceData);
            
            Files.write(testPath, baos.toByteArray());
            
            Scene scene = Scene.fromFile(testPath.toString(), new StlLoadOptions());
            assertNotNull(scene);
            
            Node rootNode = scene.getRootNode();
            assertNotNull(rootNode);
        } finally {
            Files.deleteIfExists(testPath);
        }
    }