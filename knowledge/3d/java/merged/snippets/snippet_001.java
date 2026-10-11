@Test
    public void ArrayListAdapterInVertexElementTemplate_ShouldWork() {
        TestVertexElementTemplate element = new TestVertexElementTemplate();

        assertNotNull(element.getData());
        assertEquals(0, element.getData().size());

        element.getData().add(1.5);
        element.getData().add(2.5);
        assertEquals(2, element.getData().size());

        assertEquals(1.5, element.getData().get(0), 1e-10);
        assertEquals(2.5, element.getData().get(1), 1e-10);

        element.getData().clear();
        assertEquals(0, element.getData().size());
    }