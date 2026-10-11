[Fact]
        public void CreateSceneWithLambertMaterial_ShouldCreateValidMaterial()
        {
            // Arrange - Create a Lambert material
            var material = new LambertMaterial("LambertMaterial");
            
            // Act & Assert - Verify material properties
            Assert.NotNull(material);
            Assert.Equal("LambertMaterial", material.Name);
            
            // Set properties
            var color = new Vector3(0.5f, 0.5f, 0.5f);
            material.AmbientColor = color;
            material.DiffuseColor = color;
            material.EmissiveColor = color;
            material.TransparentColor = color;
            material.Transparency = 0.3;
            
            Assert.Equal(0.5f, material.AmbientColor.X);
            Assert.Equal(0.5f, material.DiffuseColor.X);
            Assert.Equal(0.3, material.Transparency);
        }