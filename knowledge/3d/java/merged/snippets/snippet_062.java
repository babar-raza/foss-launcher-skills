@Test
    public void setData_ShouldSetData() {
        TestVertexElementTemplate element = new TestVertexElementTemplate();
        Double[] data = {1.0, 2.0, 3.0};

        element.setData(data);

        assertEquals(3, element.getData().size());
        assertEquals(1.0, element.getData().get(0), 1e-10);
        assertEquals(2.0, element.getData().get(1), 1e-10);
        assertEquals(3.0, element.getData().get(2), 1e-10);
    }