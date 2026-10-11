[Fact]
        public void CurveType_ShouldBeSettable()
        {
            var curve = new NurbsCurve();
            curve.CurveType = NurbsType.Closed;
            
            Assert.Equal(NurbsType.Closed, curve.CurveType);
        }