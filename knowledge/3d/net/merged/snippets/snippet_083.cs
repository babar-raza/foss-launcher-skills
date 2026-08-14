[Fact]
        public void KnotVectors_ShouldBeWritable()
        {
            var curve = new NurbsCurve();
            var knotVectors = curve.KnotVectors;
            
            Assert.NotNull(knotVectors);
            Assert.Empty(knotVectors);
            
            knotVectors.Add(0.0);
            knotVectors.Add(1.0);
            Assert.Equal(2, knotVectors.Count);
        }