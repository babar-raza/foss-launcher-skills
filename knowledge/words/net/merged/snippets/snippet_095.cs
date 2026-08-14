[Test]
        public void TestAddingSeriesWithDateTimeX()
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
                        new DateTime[] { new DateTime(2020, 1, 1), new DateTime(2020, 3, 1),
                            new DateTime(2020, 6, 1), new DateTime(2020, 12, 1) },
                        new double[] { 10, 7, 12, 15 });
                }

                TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestAddingSeriesWithDateTimeX.docx");
            }
            finally
            {
                SystemPal.RestoreCulture();
            }
        }