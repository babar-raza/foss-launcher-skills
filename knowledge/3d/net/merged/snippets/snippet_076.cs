[Fact]
        public void PbrMaterial_AlbedoConstructor_ShouldCreateInstance()
        {
            var material = new PbrMaterial(new Vector3(1.0f, 0.5f, 0.2f));
            
            Assert.NotNull(material);
            Assert.Equal(1.0f, material.Albedo.X);
            Assert.Equal(0.5f, material.Albedo.Y);
            Assert.Equal(0.2f, material.Albedo.Z);
        }