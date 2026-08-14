[Test]
        public void TestAddingSeriesWithBubbleSize()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            foreach (ChartType chartType in Enum.GetValues(typeof(ChartType)))
            {
                Shape shape = builder.InsertChart(chartType, 432, 252);
                Chart chart = shape.Chart;

                chart.Title.Text = chartType.ToString();
                chart.Series.Clear();

                chart.Series.Add(
                    "Series 1",
                    new double[] { 1, 2.5, 3.5, 5 },
                    new double[] { 10, 7, 12, 15 },
                    new double[] { 1, 0.75, 1.25, 2 });
            }

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestAddingSeriesWithBubbleSize.docx");
        }