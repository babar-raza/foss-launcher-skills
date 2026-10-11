[Fact]
        public void Multiplicity_ShouldBeWritable()
        {
            var curve = new NurbsCurve();
            var multiplicity = curve.Multiplicity;
            
            Assert.NotNull(multiplicity);
            Assert.Empty(multiplicity);
            
            multiplicity.Add(2);
            Assert.Single(multiplicity);
        }