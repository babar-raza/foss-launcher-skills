[Fact]
        public void LambertMaterial_NameConstructor_ShouldSetName()
        {
            var material = new LambertMaterial("TestMaterial");
            
            Assert.Equal("TestMaterial", material.Name);
        }