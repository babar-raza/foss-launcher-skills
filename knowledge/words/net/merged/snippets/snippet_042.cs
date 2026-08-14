[Test]
        public void TestPosition()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            List<ChartDataLabelPosition> supportedPositions = new List<ChartDataLabelPosition>();

            // Box&Whisker chart has many labels, let's set each position value to two labels.
            int[] boxWhiskerLabelStartIndexes = new[] { 9, 20, 30 };
            const int boxWhiskerNextTestLabelOffset = 2;

            foreach (ChartSeriesType seriesType in Enum.GetValues(typeof(ChartSeriesType)))
            {
                // These series types has no corresponding chart type; charts of these types cannot be created: skip them.
                if ((seriesType == ChartSeriesType.ParetoLine) || (seriesType == ChartSeriesType.RegionMap))
                    continue;

                if (!FillSupportedPositions(seriesType, supportedPositions))
                    continue;

                ChartType chartType = DmlChartUtil.SeriesTypeToChartType(seriesType);
                Shape shape = builder.InsertChart(chartType, 432, 252);
                Chart chart = shape.Chart;

                chart.Title.Text = chartType.ToString();

                // Prepare necessary number of data labels.

                ChartSeriesCollection seriesCollection = chart.Series;
                if (seriesType != ChartSeriesType.Stock)
                {
                    while (seriesCollection.Count > 1)
                        seriesCollection.RemoveAt(seriesCollection.Count - 1);
                }

                ChartSeries series =  seriesCollection[0];
                if (seriesType != ChartSeriesType.Histogram)
                {
                    while (series.ValueCount < supportedPositions.Count)
                    {
                        ChartXValue xValue = GetNewXValue(series);
                        ChartYValue yValue = ChartYValue.FromDouble(series.ValueCount);
                        if ((seriesType == ChartSeriesType.Bubble) || (seriesType == ChartSeriesType.Bubble3D))
                            series.Add(xValue, yValue, series.BubbleSizes[0]);
                        else
                            series.Add(xValue, yValue);
                    }

                    if (!chart.ChartSpace.IsChartEx && (seriesType != ChartSeriesType.PieOfPie) &&
                        (seriesType != ChartSeriesType.PieOfBar))
                    {
                        while (series.ValueCount > supportedPositions.Count)
                            series.Remove(series.ValueCount - 1);
                    }
                }

                // Show data labels and set their positions.

                series.HasDataLabels = true;
                ChartDataLabelCollection dataLabels = series.DataLabels;
                dataLabels.Position = supportedPositions[0];
                if (seriesType == ChartSeriesType.BoxAndWhisker)
                {
                    for (int i = 1; i < supportedPositions.Count; i++)
                    {
                        for (int j = 0; j <= 2; j += boxWhiskerNextTestLabelOffset)
                            dataLabels[boxWhiskerLabelStartIndexes[i - 1] + j].Position = supportedPositions[i];
                    }
                }
                else
                {
                    for (int i = 0; i < supportedPositions.Count; i++)
                    {
                        ChartDataLabel label = dataLabels[i];

                        // Write position value as label text (it doesn't work for Word 2016 charts).
                        if (!chart.ChartSpace.IsChartEx)
                        {
                            label.LabelPr.SetProperty(
                                DmlChartDataLabelAttrs.Tx,
                                DmlChartRenderingUtil.CreateTx(supportedPositions[i].ToString()));
                        }

                        // The first label gets value from the collection.
                        if (i > 0)
                            label.Position = supportedPositions[i];
                    }
                }
            }

            doc = TestUtil.SaveOpenDocxExportOnly(doc, @"Model\Charts\TestDataLabelPosition.docx");

            // Check the positions after saving/opening.

            foreach (Shape shape in doc.FirstSection.Body.Shapes)
            {
                ChartSeries series = shape.Chart.Series[0];
                FillSupportedPositions(series.SeriesType, supportedPositions);
                Assert.That(supportedPositions.Count > 0, Is.True);

                ChartDataLabelCollection dataLabels = series.DataLabels;
                Assert.That(dataLabels.Position, Is.EqualTo(supportedPositions[0]));
                if (series.SeriesType == ChartSeriesType.BoxAndWhisker)
                {
                    for (int i = 1; i < supportedPosition