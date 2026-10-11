[Fact]
        public void ConstructorWithName_ShouldInitializeWithName()
        {
            var curve = new NurbsCurve("TestCurve");
            
            Assert.Equal("TestCurve", curve.Name);
        }