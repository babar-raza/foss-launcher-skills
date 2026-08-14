[Fact]
        public void Dimension_ShouldBeSettable()
        {
            var curve = new NurbsCurve();
            curve.Dimension = CurveDimension.TwoDimensional;
            
            Assert.Equal(CurveDimension.TwoDimensional, curve.Dimension);
        }