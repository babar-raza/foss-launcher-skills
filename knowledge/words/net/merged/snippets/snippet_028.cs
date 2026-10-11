[Test]
        public void TestDataLabelCountWithOutsideLabel()
        {
            Document doc = CreateDocumentWithChart();
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;
            ChartSeries series = chart.Series[0];

            CheckLabelCount(series, 0);

            series.HasDataLabels = true;
            CheckLabelCount(series, 3);

            ChartDataLabel label = series.DataLabels[5];
            CheckLabelCount(series, 3);

            label.ShowCategoryName = true;
            // Now the label #5 has non-default value and is included in Count value.
            CheckLabelCount(series, 4);
        }