[Fact]
        public void EvaluateAt_ShouldThrowNotImplementedException()
        {
            var curve = new NurbsCurve();
            
            Assert.Throws<NotImplementedException>(() => curve.EvaluateAt(0.5));
        }