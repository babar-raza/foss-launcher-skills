[Fact]
        public void Divisions_ShouldBeSettable()
        {
            var direction = new NurbsDirection();
            direction.Divisions = 20;
            
            Assert.Equal(20, direction.Divisions);
        }