[Test]
        public void TestAddingSeriesWithoutY()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            foreach (ChartType chartType in Enum.GetValues(typeof(ChartType)))
            {
                Shape shape = builder.InsertChart(chartType, 432, 252);
                Chart chart = shape.Chart;

                chart.Title.Text = chartType.ToString();
                chart.Series.Clear();

                chart.Series.Add("Series 1", new double[] { 10, 7, 12, 15, 14, 11 });
            }

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestAddingSeriesWithoutY.docx");
        }