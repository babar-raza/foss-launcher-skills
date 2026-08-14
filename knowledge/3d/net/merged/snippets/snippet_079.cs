[Fact]
        public void Constructor_ShouldInitializeDefaultValues()
        {
            var curve = new NurbsCurve();
            
            Assert.NotNull(curve);
            Assert.Equal(2, curve.Order);
            Assert.Equal(1, curve.Degree);
            Assert.False(curve.Rational);
            Assert.Equal(CurveDimension.ThreeDimensional, curve.Dimension);
            Assert.Equal(NurbsType.Open, curve.CurveType);
        }