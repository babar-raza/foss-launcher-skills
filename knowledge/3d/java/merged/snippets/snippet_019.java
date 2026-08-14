@Test
    public void lambertMaterial_NameConstructor_ShouldSetName() {
        LambertMaterial material = new LambertMaterial("TestMaterial");

        assertEquals("TestMaterial", material.getName());
    }