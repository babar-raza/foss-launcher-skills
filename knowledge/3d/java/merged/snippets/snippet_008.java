@Test
    public void openStreamWithAutoDetectionObj_ShouldLoadCorrectly() throws IOException {
        String testFile = "testdata/input/cube.obj";

        File file = new File(testFile);
        if (!file.exists()) {
            throw new IOException("Test file not found: " + testFile);
        }

        FileInputStream stream = new FileInputStream(file);
        Scene scene = new Scene();
        FileFormat format = FileFormat.getFormatByExtension(".obj");
        scene.open(Stream.wrap(stream), format);

        stream.close();
        assertNotNull(scene);
        assertNotNull(scene.getRootNode());
        assertTrue(scene.getRootNode().getChildNodes().size() > 0);

        Node node = scene.getRootNode().getChildNodes().get(0);
        assertNotNull(node.getEntities());
        assertTrue(node.getEntities().size() > 0);

        Mesh mesh = (Mesh) node.getEntities().get(0);
        assertNotNull(mesh);
        assertEquals(8, mesh.getControlPoints().size());
        assertEquals(3, mesh.getPolygonCount());
    }