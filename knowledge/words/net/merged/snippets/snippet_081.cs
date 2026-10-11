[Test]
        [ExpectedException(typeof(InvalidOperationException),
            ExpectedMessage = "The property is not supported on a chart object.")]
        public void TestUnsupportedFontProperties()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);

            ChartSeries series = shape.Chart.Series[0];
            Font font = series.LegendEntry.Font;

            // Throws an exception.
            font.ThemeColor = ThemeColor.Accent1;
        }