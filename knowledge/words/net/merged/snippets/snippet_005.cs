[Test]
        public void TestEquals()
        {
            AxisBound bound1 = new AxisBound(1d);
            AxisBound bound2 = new AxisBound(1d);
            AxisBound bound3 = new AxisBound(1.00001d);
            Assert.That(bound1.Equals(bound2), Is.True);
            Assert.That(bound2.Equals(bound1), Is.True);
            Assert.That(bound1.Equals(bound3), Is.False);
            Assert.That(bound3.Equals(bound1), Is.False);
            Assert.That(bound1.Equals(new AxisBound()), Is.False);

            bound1 = new AxisBound(DateTime.Today);
            bound2 = new AxisBound(DateTime.Today);
            Assert.That(bound1.Equals(bound2), Is.True);
            Assert.That(bound2.Equals(bound1), Is.True);
            Assert.That(bound1.Equals(new AxisBound()), Is.False);

            bound1 = new AxisBound();
            bound2 = new AxisBound();
            Assert.That(bound1.Equals(bound2), Is.True);
            Assert.That(bound2.Equals(bound1), Is.True);
        }