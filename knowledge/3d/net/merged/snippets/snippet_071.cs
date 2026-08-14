[Fact]
        public void LambertMaterial_Properties_ShouldBeSettable()
        {
            var material = new LambertMaterial();
            var color = new Vector3(0.5f, 0.5f, 0.5f);
            
            material.EmissiveColor = color;
            material.AmbientColor = color;
            material.DiffuseColor = color;
            material.TransparentColor = color;
            material.Transparency = 0.3;
            
            Assert.Equal(0.5f, material.EmissiveColor.X);
            Assert.Equal(0.5f, material.AmbientColor.X);
            Assert.Equal(0.5f, material.DiffuseColor.X);
            Assert.Equal(0.5f, material.TransparentColor.X);
            Assert.Equal(0.3, material.Transparency);
        }