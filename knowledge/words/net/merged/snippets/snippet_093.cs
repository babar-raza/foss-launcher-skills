[Test]
        public void TestAddingSeriesWithStringX()
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
                    new string[] { "Category 1", "Category 2", "Category 3", "Category 4" },
                    new double[] { 10, 7, 12, 15 });
            }

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestAddingSeriesWithStringX.docx");
        }