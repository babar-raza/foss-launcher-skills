@Test
    public void testSceneCreation() {
        Scene scene = new Scene();
        assertNotNull(scene.getRootNode());
        assertEquals("RootNode", scene.getRootNode().getName());
    }