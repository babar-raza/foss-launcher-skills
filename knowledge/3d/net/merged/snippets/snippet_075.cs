[Fact]
        public void PbrMaterial_DefaultConstructor_ShouldCreateInstance()
        {
            var material = new PbrMaterial();
            
            Assert.NotNull(material);
        }