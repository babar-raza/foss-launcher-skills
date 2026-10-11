[Test]
        public void TestCreation()
        {
            AxisBound bound = new AxisBound(1d);
            Assert.That(bound.IsAuto, Is.False);
            Assert.That(bound.Value, Is.EqualTo(1d));
            Assert.That(bound.ValueAsDate, Is.EqualTo(new DateTime(1899, 12, 31)));

            DateTime datetime = new DateTime(2018, 5, 25);
            bound = new AxisBound(datetime);
            Assert.That(bound.IsAuto, Is.False);
            Assert.That(bound.Value, Is.EqualTo(datetime.ToOADate()));
            Assert.That(bound.ValueAsDate, Is.EqualTo(datetime));

            Assert.That(new AxisBound().IsAuto, Is.True);
        }