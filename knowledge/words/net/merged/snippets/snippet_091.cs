[TestCase(ChartType.Area, ChartSeriesType.Area)]
        [TestCase(ChartType.AreaStacked, ChartSeriesType.AreaStacked)]
        [TestCase(ChartType.AreaPercentStacked, ChartSeriesType.AreaPercentStacked)]
        [TestCase(ChartType.Area3D, ChartSeriesType.Area3D)]
        [TestCase(ChartType.Area3DStacked, ChartSeriesType.Area3DStacked)]
        [TestCase(ChartType.Area3DPercentStacked, ChartSeriesType.Area3DPercentStacked)]
        [TestCase(ChartType.Bar, ChartSeriesType.Bar)]
        [TestCase(ChartType.BarStacked, ChartSeriesType.BarStacked)]
        [TestCase(ChartType.BarPercentStacked, ChartSeriesType.BarPercentStacked)]
        [TestCase(ChartType.Bar3D, ChartSeriesType.Bar3D)]
        [TestCase(ChartType.Bar3DStacked, ChartSeriesType.Bar3DStacked)]
        [TestCase(ChartType.Bar3DPercentStacked, ChartSeriesType.Bar3DPercentStacked)]
        [TestCase(ChartType.Bubble, ChartSeriesType.Bubble)]
        [TestCase(ChartType.Bubble3D, ChartSeriesType.Bubble3D)]
        [TestCase(ChartType.Column, ChartSeriesType.Column)]
        [TestCase(ChartType.ColumnStacked, ChartSeriesType.ColumnStacked)]
        [TestCase(ChartType.ColumnPercentStacked, ChartSeriesType.ColumnPercentStacked)]
        [TestCase(ChartType.Column3D, ChartSeriesType.Column3D)]
        [TestCase(ChartType.Column3DStacked, ChartSeriesType.Column3DStacked)]
        [TestCase(ChartType.Column3DPercentStacked, ChartSeriesType.Column3DPercentStacked)]
        [TestCase(ChartType.Column3DClustered, ChartSeriesType.Column3DClustered)]
        [TestCase(ChartType.Doughnut, ChartSeriesType.Doughnut)]
        [TestCase(ChartType.LineStacked, ChartSeriesType.LineStacked)]
        [TestCase(ChartType.LinePercentStacked, ChartSeriesType.LinePercentStacked)]
        [TestCase(ChartType.Line3D, ChartSeriesType.Line3D)]
        [TestCase(ChartType.Pie, ChartSeriesType.Pie)]
        [TestCase(ChartType.Pie3D, ChartSeriesType.Pie3D)]
        [TestCase(ChartType.PieOfBar, ChartSeriesType.PieOfBar)]
        [TestCase(ChartType.PieOfPie, ChartSeriesType.PieOfPie)]
        [TestCase(ChartType.Radar, ChartSeriesType.Radar)]
        [TestCase(ChartType.Scatter, ChartSeriesType.Scatter)]
        [TestCase(ChartType.Stock, ChartSeriesType.Stock)]
        [TestCase(ChartType.Surface, ChartSeriesType.Surface)]
        [TestCase(ChartType.Surface3D, ChartSeriesType.Surface3D)]
        public void TestNonWord2016ChartSeriesType(ChartType chartType, ChartSeriesType expectedSeriesType)
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(chartType, 432, 252);

            foreach (ChartSeries series in shape.Chart.Series)
                Assert.That(series.SeriesType, Is.EqualTo(expectedSeriesType));
        }