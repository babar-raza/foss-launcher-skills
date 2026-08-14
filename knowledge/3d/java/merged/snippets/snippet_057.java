@Test
    public void testAdd() {
        Vector3 a = new Vector3(1, 2, 3);
        Vector3 b = new Vector3(4, 5, 6);
        Vector3 c = Vector3.add(a, b);
        assertEquals(5, c.x);
        assertEquals(7, c.y);
        assertEquals(9, c.z);
    }