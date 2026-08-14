@Test
    public void constructorWithName_ShouldInitializeWithName() {
        NurbsCurve curve = new NurbsCurve("TestCurve");

        assertEquals("TestCurve", curve.getName());
    }