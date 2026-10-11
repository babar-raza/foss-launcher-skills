[Fact]
        public void Count_ShouldBeSettable()
        {
            var direction = new NurbsDirection();
            direction.Count = 8;
            
            Assert.Equal(8, direction.Count);
        }