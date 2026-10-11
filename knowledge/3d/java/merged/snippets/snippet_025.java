@Test
    public void pbrMaterial_Properties_ShouldBeSettable() {
        PbrMaterial material = new PbrMaterial();
        Vector3 albedo = new Vector3(1.0f, 0.5f, 0.2f);

        material.setAlbedo(albedo);
        material.setMetallicFactor(0.8);
        material.setRoughnessFactor(0.2);
        material.setOcclusionFactor(0.9);
        material.setTransparency(0.5);

        assertEquals(1.0f, material.getAlbedo().x, 1e-10);
        assertEquals(0.8, material.getMetallicFactor(), 1e-10);
        assertEquals(0.2, material.getRoughnessFactor(), 1e-10);
        assertEquals(0.9, material.getOcclusionFactor(), 1e-10);
        assertEquals(0.5, material.getTransparency(), 1e-10);
    }