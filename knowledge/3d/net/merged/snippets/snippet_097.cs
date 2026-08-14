[Fact]
        public void Type_ShouldBeSettable()
        {
            var direction = new NurbsDirection();
            direction.Type = NurbsType.Closed;
            
            Assert.Equal(NurbsType.Closed, direction.Type);
        }