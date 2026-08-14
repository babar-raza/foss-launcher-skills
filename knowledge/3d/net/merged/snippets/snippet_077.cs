[Fact]
        public void PbrMaterial_Properties_ShouldBeSettable()
        {
            var material = new PbrMaterial();
            var albedo = new Vector3(1.0f, 0.5f, 0.2f);
            
            material.Albedo = albedo;
            material.MetallicFactor = 0.8;
            material.RoughnessFactor = 0.2;
            material.OcclusionFactor = 0.9;
            material.Transparency = 0.5;
            
            Assert.Equal(1.0f, material.Albedo.X);
            Assert.Equal(0.8, material.MetallicFactor);
            Assert.Equal(0.2, material.RoughnessFactor);
            Assert.Equal(0.9, material.OcclusionFactor);
            Assert.Equal(0.5, material.Transparency);
        }