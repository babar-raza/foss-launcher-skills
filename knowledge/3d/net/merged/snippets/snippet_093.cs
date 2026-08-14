[Fact]
        public void Multiplicity_ShouldBeWritable()
        {
            var direction = new NurbsDirection();
            var multiplicity = direction.Multiplicity;
            
            Assert.NotNull(multiplicity);
            Assert.Empty(multiplicity);
            
            multiplicity.Add(2);
            Assert.Single(multiplicity);
        }