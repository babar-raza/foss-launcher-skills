@Test
    public void lambertMaterial_Properties_ShouldBeSettable() {
        LambertMaterial material = new LambertMaterial();
        Vector3 color = new Vector3(0.5f, 0.5f, 0.5f);

        material.setEmissiveColor(color);
        material.setAmbientColor(color);
        material.setDiffuseColor(color);
        material.setTransparentColor(color);
        material.setTransparency(0.3);

        assertEquals(0.5f, material.getEmissiveColor().x, 1e-10);
        assertEquals(0.5f, material.getAmbientColor().x, 1e-10);
        assertEquals(0.5f, material.getDiffuseColor().x, 1e-10);
        assertEquals(0.5f, material.getTransparentColor().x, 1e-10);
        assertEquals(0.3, material.getTransparency(), 1e-10);
    }