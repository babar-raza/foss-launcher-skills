[Test]
        public void TestOverflowAsDate()
        {
            AxisBound bound1 = new AxisBound(10000000);
            Assert.That(bound1.ValueAsDate, Is.EqualTo(DateTime.MinValue));

            AxisBound bound2 = new AxisBound(-10000000);
            Assert.That(bound2.ValueAsDate, Is.EqualTo(DateTime.MinValue));
        }