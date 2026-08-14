[Fact]
        public void PbrMaterial_FromMaterial_ShouldCreateInstance()
        {
            var material = new LambertMaterial();
            var pbr = PbrMaterial.FromMaterial(material);
            
            Assert.NotNull(pbr);
        }