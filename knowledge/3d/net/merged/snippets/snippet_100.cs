[Fact]
        public void CreateSceneWithPhongMaterial_ShouldCreateValidMaterial()
        {
            // Arrange - Create a Phong material
            var material = new PhongMaterial("PhongMaterial");
            
            // Act & Assert - Verify material properties
            Assert.NotNull(material);
            Assert.Equal("PhongMaterial", material.Name);
            
            // Set properties
            material.SpecularColor = new Vector3(0.8f, 0.8f, 0.8f);
            material.Shininess = 50.0;
            material.SpecularFactor = 0.8;
            material.ReflectionColor = new Vector3(0.3f, 0.3f, 0.3f);
            material.ReflectionFactor = 0.5;
            
            Assert.Equal(0.8f, material.SpecularColor.X);
            Assert.Equal(50.0, material.Shininess);
            Assert.Equal(0.5, material.ReflectionFactor);
        }