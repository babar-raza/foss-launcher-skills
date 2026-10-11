[Fact]
        public void ControlPoints_ShouldBeWritable()
        {
            var curve = new NurbsCurve();
            var controlPoints = curve.ControlPoints;
            
            Assert.NotNull(controlPoints);
            Assert.Empty(controlPoints);
            
            controlPoints.Add(new Vector4(1, 2, 3, 1));
            Assert.Single(controlPoints);
        }