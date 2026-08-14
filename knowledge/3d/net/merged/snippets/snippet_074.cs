[Fact]
        public void PhongMaterial_Properties_ShouldBeSettable()
        {
            var material = new PhongMaterial();
            var specularColor = new Vector3(0.8f, 0.8f, 0.8f);
            
            material.SpecularColor = specularColor;
            material.Shininess = 50.0;
            material.SpecularFactor = 1.0;
            material.ReflectionColor = new Vector3(0.2f, 0.2f, 0.2f);
            material.ReflectionFactor = 0.5;
            
            Assert.Equal(0.8f, material.SpecularColor.X);
            Assert.Equal(50.0, material.Shininess);
            Assert.Equal(1.0, material.SpecularFactor);
            Assert.Equal(0.2f, material.ReflectionColor.X);
            Assert.Equal(0.5, material.ReflectionFactor);
        }