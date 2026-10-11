[Test]
        public void TestHidingChartDataLabel()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Line, 432, 252);
            Chart chart = shape.Chart;
            ChartSeries series = chart.Series[0];

            Assert.That(series.HasDataLabels, Is.False);

            series.HasDataLabels = true;

            ChartDataLabel label1 = series.DataLabels[1];
            ChartDataLabel label2 = series.DataLabels[2];
            Assert.That(label1.IsHidden, Is.False);

            label1.IsHidden = true;
            label2.IsHidden = false;

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestDeletingChartDataLabel.docx", null, false);

            shape = doc.FirstSection.Body.Shapes[0];
            chart = shape.Chart;
            series = chart.Series[0];

            Assert.That(series.HasDataLabels, Is.True);

            label1 = series.DataLabels[1];
            label2 = series.DataLabels[2];

            Assert.That(label1.IsHidden, Is.True);
            Assert.That(label2.IsHidden, Is.False);
        }