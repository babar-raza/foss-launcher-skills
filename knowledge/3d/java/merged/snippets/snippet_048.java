@Test
    public void testNodeCreation() {
        Scene scene = new Scene();
        Node node = scene.getRootNode().createChildNode("TestNode");
        assertNotNull(node);
        assertEquals("TestNode", node.getName());
        assertEquals(1, scene.getRootNode().getChildNodes().size());
    }