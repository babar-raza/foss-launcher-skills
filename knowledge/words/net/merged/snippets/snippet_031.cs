[Test]
        public void TestDataLabelClearFormat()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Line, 432, 252);
            Chart chart = shape.Chart;
            ChartSeries series = chart.Series[0];
            series.HasDataLabels = true;

            ChartDataLabelCollection labels = chart.Series[0].DataLabels;
            ChartDataLabel label = labels[1];

            labels.ShowValue = true;

            Assert.That(label.ShowDataLabelsRange, Is.False);
            Assert.That(label.ShowValue, Is.True);

            label.ShowDataLabelsRange = true;
            label.ShowValue = false;

            Assert.That(label.ShowDataLabelsRange, Is.True);
            Assert.That(label.ShowValue, Is.False);

            label.ClearFormat();

            Assert.That(label.ShowDataLabelsRange, Is.False);
            Assert.That(label.ShowValue, Is.True);
        }