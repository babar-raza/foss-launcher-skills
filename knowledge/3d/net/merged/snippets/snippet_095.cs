[Fact]
        public void Degree_ShouldBeSettable()
        {
            var direction = new NurbsDirection();
            direction.Degree = 2;
            
            Assert.Equal(2, direction.Degree);
        }