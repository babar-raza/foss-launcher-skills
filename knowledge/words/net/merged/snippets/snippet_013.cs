[Test]
        public void Test24673()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Bar, 432, 252);
            Chart chart = shape.Chart;
            chart.Legend.Position = LegendPosition.None;

            ChartSeriesCollection seriesColl = chart.Series;
            chart.AxisY.Hidden = true;
            chart.AxisY.HasMajorGridlines = false;
            chart.AxisX.Hidden = true;
            chart.Title.Show = false;

            seriesColl.Clear();
            chart.AxisY.Scaling.Maximum = new AxisBound(100);

            string[] categories = new string[] { "AW Category 1" };
            seriesColl.Add("AW Series 1", categories, new double[] { 30 });

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\Test24673.docx");
        }