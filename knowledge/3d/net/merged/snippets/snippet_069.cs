[Fact]
        public void LambertMaterial_DefaultConstructor_ShouldCreateInstance()
        {
            var material = new LambertMaterial();
            
            Assert.NotNull(material);
        }