private static void CheckLabelCount(ChartSeries series, int expectedCount)
        {
            Assert.That(series.DataLabels.Count, Is.EqualTo(expectedCount));

            // Check enumerator too.
            int count = 0;
            foreach (ChartDataLabel label in series.DataLabels)
                count++;
            Assert.That(count, Is.EqualTo(expectedCount));
        }