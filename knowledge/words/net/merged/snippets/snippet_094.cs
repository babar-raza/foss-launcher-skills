[Test]
        public void TestAddingSeriesWithDoubleX()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);
            SystemPal.SaveCulture();
            try
            {
                SystemPal.SetStandardCulture();

                    foreach (ChartType chartType in Enum.GetValues(typeof(ChartType)))
                {
                    Shape shape = builder.InsertChart(chartType, 432, 252);
                    Chart chart = shape.Chart;

                    chart.Title.Text = chartType.ToString();
                    chart.Series.Clear();

                    chart.Series.Add(
                        "Series 1",
                        new double[] { 1, 2.5, 4, 5.5 },
                        new double[] { 10, 7, 12, 15 });
                }

              TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestAddingSeriesWithDoubleX.docx");
            }
            finally
            {
                SystemPal.RestoreCulture();
            }
        }