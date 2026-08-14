[Test]
        public void TestTimeCategoryAxis()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);
            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);
            Chart chart = shape.Chart;
            ChartAxis xAxis = chart.AxisX;

            // Expected automatic-text category type.
            Assert.That(xAxis.IsDateCategoryAxis, Is.EqualTo(false));

            // Add series with DateTime data.
            chart.Series.Add("Series 1",
                new DateTime[] { new DateTime(2017, 11, 06), new DateTime(2017, 11, 09), new DateTime(2017, 11, 15),
                    new DateTime(2017, 11, 21), new DateTime(2017, 11, 25), new DateTime(2017, 11, 29) },
                new double[] { 1.2, 0.3, 2.1, 2.9, 4.2, 5.3 });

            // Expected automatic-date/time category type.
            Assert.That(xAxis.IsDateCategoryAxis, Is.EqualTo(true));

            chart.Series.Clear();

            // Expected automatic-text category type.
            Assert.That(xAxis.IsDateCategoryAxis, Is.EqualTo(false));
        }