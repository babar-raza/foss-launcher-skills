private static void CheckPointCount(ChartSeries series, int expectedCount)
        {
            Assert.That(series.DataPoints.Count, Is.EqualTo(expectedCount));

            // Check enumerator too.
            int count = 0;
            foreach (ChartDataPoint point in series.DataPoints)
                count++;
            Assert.That(count, Is.EqualTo(expectedCount));
        }