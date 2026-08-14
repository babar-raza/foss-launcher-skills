[Test]
        public void TestDifferentLocationModes()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);
            Chart chart = shape.Chart;

            foreach (ChartSeries series in chart.Series)
            {
                series.HasDataLabels = true;
                ChartDataLabelCollection dataLabels = series.DataLabels;
                dataLabels.ShowValue = true;
                dataLabels.Position = ChartDataLabelPosition.OutsideEnd;

                foreach (ChartDataLabel dataLabel in dataLabels)
                {
                    dataLabel.LeftMode = ChartDataLabelLocationMode.Offset;
                    dataLabel.Left = 1.5;
                    dataLabel.TopMode = ChartDataLabelLocationMode.Absolute;
                    dataLabel.Top = 93;
                }
            }

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestDataLabelDifferentLocationModes.docx");
        }