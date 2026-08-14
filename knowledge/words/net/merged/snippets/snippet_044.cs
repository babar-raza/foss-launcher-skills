[Test]
        public void TestLeftTopWithRelativeCoordinates()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            // Test moving data labels of a bar chart so that they are in front of bars.

            Shape shape = builder.InsertChart(ChartType.Bar, 432, 252);
            Chart chart = shape.Chart;
            chart.AxisX.Hidden = true;
            chart.AxisY.Scaling.Minimum = new AxisBound(-1);

            // Let's move the data labels so they are further apart vertically.
            const double verticalMovePerLabel = 0.75;
            double topOffset = (chart.Series.Count - 1) / 2 * verticalMovePerLabel;

            foreach (ChartSeries series in chart.Series)
            {
                series.HasDataLabels = true;
                ChartDataLabelCollection dataLabels = series.DataLabels;
                dataLabels.ShowValue = true;
                dataLabels.ShowLeaderLines = false;
                dataLabels.Position = ChartDataLabelPosition.InsideBase;

                foreach (ChartDataLabel dataLabel in dataLabels)
                {
                    dataLabel.LeftMode = ChartDataLabelLocationMode.Offset;
                    dataLabel.Left = -27;
                    dataLabel.TopMode = ChartDataLabelLocationMode.Offset;
                    dataLabel.Top = topOffset;
                }

                topOffset -= verticalMovePerLabel;
            }

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestDataLabelLeftTopWithRelativeCoordinates.docx");
        }