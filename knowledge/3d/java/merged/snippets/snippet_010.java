@Test
    public void openStreamWithAutoDetectionGltf_ShouldLoadCorrectly() throws IOException, ImportException {
        String testFile = "testdata/gltf/simple_cube.gltf";

        File file = new File(testFile);
        if (!file.exists()) {
            throw new IOException("Test file not found: " + testFile);
        }

        FileInputStream stream = new FileInputStream(file);
        Scene scene = new Scene();
        FileFormat format = FileFormat.detect(Stream.wrap(stream), "simple_cube.gltf");
        scene.open(Stream.wrap(stream), format, format.createLoadOptions());

        stream.close();
        assertNotNull(scene);
        assertNotNull(scene.getRootNode());
    }