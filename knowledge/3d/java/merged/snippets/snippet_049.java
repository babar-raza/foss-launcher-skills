@Test
    public void testTransform() {
        Node node = new Node("Test");
        Transform t = node.getTransform();
        assertNotNull(t);
        t.setTranslation(1, 2, 3);
        assertEquals(1, t.getTranslation().x, 1e-10);
        assertEquals(2, t.getTranslation().y, 1e-10);
        assertEquals(3, t.getTranslation().z, 1e-10);
    }