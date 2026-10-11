@Test
    public void testCross() {
        Vector3 a = Vector3.getUnitX();
        Vector3 b = Vector3.getUnitY();
        Vector3 c = a.cross(b);
        assertEquals(0, c.x, 1e-10);
        assertEquals(0, c.y, 1e-10);
        assertEquals(1, c.z, 1e-10);
    }