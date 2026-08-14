@Test
    public void data_ShouldBeWritable() {
        TestVertexElementTemplate element = new TestVertexElementTemplate();

        assertNotNull(element.getData());
        assertEquals(0, element.getData().size());

        element.getData().add(1.5);
        element.getData().add(2.5);
        assertEquals(2, element.getData().size());
    }