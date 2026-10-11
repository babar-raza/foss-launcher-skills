[Test]
        public void TestPointCountWhenContainingOutsidePoint()
        {
            Document doc = CreateDocumentWithChart();
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;
            ChartSeries series = chart.Series[0];

            CheckPointCount(series, 3);

            ChartDataPoint point = series.DataPoints[5];
            CheckPointCount(series, 3);

            point.Marker.Symbol = MarkerSymbol.Plus;
            // Now the data point #5 has non-default value and is included in Count value.
            CheckPointCount(series, 4);

            series.DataPoints[5000].InvertIfNegative = true;
            CheckPointCount(series, 5);
        }