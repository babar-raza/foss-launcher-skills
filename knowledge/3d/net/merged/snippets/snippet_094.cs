[Fact]
        public void Order_ShouldBeSettable()
        {
            var direction = new NurbsDirection();
            direction.Order = 4;
            
            Assert.Equal(4, direction.Order);
        }