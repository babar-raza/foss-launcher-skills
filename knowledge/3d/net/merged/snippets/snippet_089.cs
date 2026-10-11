[Fact]
        public void Evaluate_ShouldThrowNotImplementedException()
        {
            var curve = new NurbsCurve();
            
            Assert.Throws<NotImplementedException>(() => curve.Evaluate(10));
        }