[Fact]
        public void PhongMaterial_DefaultConstructor_ShouldCreateInstance()
        {
            var material = new PhongMaterial();
            
            Assert.NotNull(material);
        }