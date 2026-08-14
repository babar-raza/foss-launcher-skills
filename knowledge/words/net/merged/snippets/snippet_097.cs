[Test]
        public void TestAddingSeriesWithMultilevelX()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            foreach (ChartType chartType in Enum.GetValues(typeof(ChartType)))
            {
                Shape shape = builder.InsertChart(chartType, 432, 252);
                Chart chart = shape.Chart;

                chart.Title.Text = chartType.ToString();
                chart.Series.Clear();

                ChartSeries series = chart.Series.Add(
                    "Series 1",
                    new ChartMultilevelValue[]
                    {
                        new ChartMultilevelValue("Branch 1", "Stem 1", "Leaf 1"),
                        new ChartMultilevelValue("Branch 1", "Stem 1", "Leaf 2"),
                        new ChartMultilevelValue("Branch 1", "Stem 1", "Leaf 3"),
                        new ChartMultilevelValue("Branch 1", "Stem 2", "Leaf 4"),
                        new ChartMultilevelValue("Branch 2", "Stem 3", "Leaf 5"),
                        new ChartMultilevelValue("Branch 2", "Stem 3", "Leaf 6"),
                    },
                    new double[] { 10, 7, 12, 15, 14, 11 });

                series.HasDataLabels = true;
                series.DataLabels.ShowValue = true;
                if ((chartType == ChartType.Treemap) || (chartType == ChartType.Sunburst))
                    series.DataLabels.ShowCategoryName = true;
            }

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestAddingSeriesWithMultilevelX.docx");
        }