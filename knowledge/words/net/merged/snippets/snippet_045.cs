[Test]
        public void TestPositionInExistingChart()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestDataLabelPosition.docx");
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;

            ChartDataLabelCollection dataLabels = chart.Series[0].DataLabels;
            Assert.That(dataLabels.Position, Is.EqualTo(ChartDataLabelPosition.Left));

            CheckDataLabelPosition(dataLabels[0], ChartDataLabelPosition.Left,
                0, ChartDataLabelLocationMode.Offset, 0, ChartDataLabelLocationMode.Offset);
            CheckDataLabelPosition(dataLabels[1], ChartDataLabelPosition.Below,
                0, ChartDataLabelLocationMode.Offset, 0, ChartDataLabelLocationMode.Offset);
            CheckDataLabelPosition(dataLabels[2], ChartDataLabelPosition.Above,
                0, ChartDataLabelLocationMode.Offset, 0, ChartDataLabelLocationMode.Offset);
            CheckDataLabelPosition(dataLabels[3], ChartDataLabelPosition.Right,
                15, ChartDataLabelLocationMode.Offset, 18, ChartDataLabelLocationMode.Offset);
            CheckDataLabelPosition(dataLabels[4], ChartDataLabelPosition.Right,
                -39.75, ChartDataLabelLocationMode.Offset, -15, ChartDataLabelLocationMode.Offset);
        }