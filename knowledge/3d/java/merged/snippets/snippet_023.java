@Test
    public void phongMaterial_Properties_ShouldBeSettable() {
        PhongMaterial material = new PhongMaterial();
        Vector3 specularColor = new Vector3(0.8f, 0.8f, 0.8f);

        material.setSpecularColor(specularColor);
        material.setShininess(50.0);
        material.setSpecularFactor(1.0);
        material.setReflectionColor(new Vector3(0.2f, 0.2f, 0.2f));
        material.setReflectionFactor(0.5);

        assertEquals(0.8f, material.getSpecularColor().x, 1e-10);
        assertEquals(50.0, material.getShininess(), 1e-10);
        assertEquals(1.0, material.getSpecularFactor(), 1e-10);
        assertEquals(0.2f, material.getReflectionColor().x, 1e-10);
        assertEquals(0.5, material.getReflectionFactor(), 1e-10);
    }