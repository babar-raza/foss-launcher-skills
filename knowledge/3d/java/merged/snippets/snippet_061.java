@Test
    public void copyTo_ShouldCopyData() {
        TestVertexElementTemplate source = new TestVertexElementTemplate();
        source.getData().add(1.5);
        source.getData().add(2.5);

        TestVertexElementTemplate target = new TestVertexElementTemplate();
        source.copyTo(target);

        assertEquals(2, target.getData().size());
        assertEquals(1.5, target.getData().get(0), 1e-10);
        assertEquals(2.5, target.getData().get(1), 1e-10);
    }