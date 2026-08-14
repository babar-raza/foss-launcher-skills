[Fact]
        public void PhongMaterial_NameConstructor_ShouldSetName()
        {
            var material = new PhongMaterial("PhongMaterial");
            
            Assert.Equal("PhongMaterial", material.Name);
        }