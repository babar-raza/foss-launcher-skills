[Fact]
        public void Rational_ShouldBeSettable()
        {
            var curve = new NurbsCurve();
            curve.Rational = true;
            
            Assert.True(curve.Rational);
        }