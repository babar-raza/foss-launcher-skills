@Test
    public void testGltfFormatDetection() {
        FileFormat gltfFormat = FileFormat.getFormatByExtension("model.gltf");
        assertNotNull(gltfFormat);
        assertTrue(gltfFormat.getCanImport());
        assertTrue(gltfFormat.getCanExport());
        
        FileFormat glbFormat = FileFormat.getFormatByExtension("model.glb");
        assertNotNull(glbFormat);
        assertTrue(glbFormat.getCanImport());
        assertTrue(glbFormat.getCanExport());
    }