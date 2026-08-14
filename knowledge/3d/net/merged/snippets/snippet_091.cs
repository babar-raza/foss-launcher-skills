[Fact]
        public void Constructor_ShouldInitializeDefaultValues()
        {
            var direction = new NurbsDirection();
            
            Assert.NotNull(direction);
            Assert.Equal(3, direction.Order);
            Assert.Equal(2, direction.Degree);
            Assert.Equal(10, direction.Divisions);
            Assert.Equal(NurbsType.Open, direction.Type);
            Assert.Equal(4, direction.Count);
        }