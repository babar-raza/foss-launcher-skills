[Test]
        public void Test25711()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            // Check font size.
            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);
            ChartSeries series = shape.Chart.Series[0];

            series.HasDataLabels = true;
            series.DataLabels.ShowValue = true;
            series.DataLabels[1].Font.Size = 15;

            Assert.That(series.DataLabels[1].Font.Size, Is.EqualTo(15).Within(0.01));

            // Check font color.
            shape = builder.InsertChart(ChartType.Column, 432, 252);
            series = shape.Chart.Series[0];

            series.HasDataLabels = true;
            series.DataLabels.ShowValue = true;
            series.DataLabels[1].Font.Color = Color.Red;

            Assert.That(series.DataLabels[1].Font.Color, Is.EqualTo(Color.FromArgb(0xff, 0, 0)));

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\Test25711.docx");
        }