@Test
    public void pbrMaterial_FromMaterial_ShouldCreateInstance() {
        LambertMaterial material = new LambertMaterial();
        PbrMaterial pbr = PbrMaterial.fromMaterial(material);

        assertNotNull(pbr);
    }