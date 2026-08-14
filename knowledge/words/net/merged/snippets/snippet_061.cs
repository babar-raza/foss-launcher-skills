private static void CheckInvertIfNegative(ChartSeries series, bool expectedSeriesValue,
            bool expectedDataPoint1Value, bool expectedDataPoint2Value)
        {
            Assert.That(series.InvertIfNegative, Is.EqualTo(expectedSeriesValue));
            Assert.That(series.DataPoints[0].InvertIfNegative, Is.EqualTo(expectedDataPoint1Value));
            Assert.That(series.DataPoints[1].InvertIfNegative, Is.EqualTo(expectedDataPoint2Value));
        }