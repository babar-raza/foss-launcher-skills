@Test
    public void detectGltfFormatFromStream_ShouldReturnGltfFormat() throws IOException {
        String testFile = "testdata/gltf/simple_cube.gltf";

        File file = new File(testFile);
        if (!file.exists()) {
            throw new IOException("Test file not found: " + testFile);
        }

        FileInputStream stream = new FileInputStream(file);
        FileFormat format = FileFormat.detect(Stream.wrap(stream), "test.gltf");
        stream.close();

        assertEquals("gltf", format.getExtension());
    }