[Test]
        public void TestAddingSeriesWithIsSubtotal()
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
                    new string[] { "Start Total", "Category 1", "Category 2", "Category 3", "End Total" },
                    new double[] { 100, 7, -12, 15, 110 },
                    new bool[] { true, false, false, false, true });
            }

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestAddingSeriesWithIsSubtotal.docx");
        }