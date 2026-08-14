@Test
    public void clear_ShouldClearData() {
        TestVertexElementTemplate element = new TestVertexElementTemplate();
        element.getData().add(1.0);
        element.getData().add(2.0);

        element.clear();

        assertEquals(0, element.getData().size());
    }