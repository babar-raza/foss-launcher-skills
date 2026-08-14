[Test]
        public void Test20203()
        {
            Document doc = CreateDocumentWithChart();
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;

            ChartSeries series = chart.Series[0];

            series.HasDataLabels = true;
            series.DataLabels.ShowValue = true;
            series.DataLabels.LabelPr.SetProperty(DmlChartDataLabelAttrs.DLblPos, ChartDataLabelPosition.Above);

            ChartDataLabel label = series.DataLabels[1];
            label.ShowCategoryName = true;
            label.Position = ChartDataLabelPosition.Below;
            Assert.That(label.ShowValue, Is.True); // Inherited value is retrieved.

            // It is expected that value and category name are displayed in the second data label.
            TestUtil.Save(doc, @"Model\Charts\Test20203.docx", null, true, GoldLevel.ExportOnly);
        }