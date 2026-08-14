[Test]
        public void TestClearFormat()
        {
            Document doc = CreateDocumentWithChart();
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;

            ChartSeries series = chart.Series[0];
            ChartDataPointCollection points = series.DataPoints;

            ChartDataPoint point1 = points[0];
            ChartDataPoint point2 = points[1];

            point1.InvertIfNegative = true;
            point1.Marker.Symbol = MarkerSymbol.Square;
            point2.InvertIfNegative = true;
            point2.Marker.Symbol = MarkerSymbol.Diamond;

            point1.ClearFormat();

            Assert.That(point1.InvertIfNegative, Is.False);
            Assert.That(point1.Marker.Symbol, Is.EqualTo(series.DefaultDataPoint.Marker.Symbol));

            points.ClearFormat();
            Assert.That(point2.InvertIfNegative, Is.False);
            Assert.That(point2.Marker.Symbol, Is.EqualTo(series.DefaultDataPoint.Marker.Symbol));
        }