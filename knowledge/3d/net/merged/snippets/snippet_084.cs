[Fact]
        public void Order_ShouldBeSettable()
        {
            var curve = new NurbsCurve();
            curve.Order = 4;
            
            Assert.Equal(4, curve.Order);
            Assert.Equal(3, curve.Degree);
        }