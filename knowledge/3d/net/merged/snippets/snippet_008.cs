[Fact]
        public void ColladaSaveOptions_HasRequiredProperties()
        {
            var options = new Fmt.ColladaSaveOptions();
            
            Assert.NotNull(options);
            Assert.False(options.Indented);
            Assert.Equal(Fmt.ColladaTransformStyle.Components, options.TransformStyle);
        }