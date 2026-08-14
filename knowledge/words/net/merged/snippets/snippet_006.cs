[Test]
        [ExpectedException(typeof(ArgumentOutOfRangeException))]
        public void TestCreationWithWrongDate()
        {
            new AxisBound(DateTime.MinValue);
        }