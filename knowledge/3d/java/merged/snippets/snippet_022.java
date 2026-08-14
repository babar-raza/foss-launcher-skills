@Test
    public void phongMaterial_NameConstructor_ShouldSetName() {
        PhongMaterial material = new PhongMaterial("PhongMaterial");

        assertEquals("PhongMaterial", material.getName());
    }