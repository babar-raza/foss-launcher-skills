[Fact]
        public void Degree_ShouldBeSettable()
        {
            var curve = new NurbsCurve();
            curve.Degree = 2;
            
            Assert.Equal(3, curve.Order);
            Assert.Equal(2, curve.Degree);
        }