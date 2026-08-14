@Test
    public void testConstructor() {
        Vector3 v = new Vector3(1, 2, 3);
        assertEquals(1, v.x);
        assertEquals(2, v.y);
        assertEquals(3, v.z);
    }