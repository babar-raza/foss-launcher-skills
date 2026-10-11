@Test
    public void testDot() {
        Vector3 a = new Vector3(1, 2, 3);
        Vector3 b = new Vector3(4, 5, 6);
        assertEquals(32, a.dot(b));
    }