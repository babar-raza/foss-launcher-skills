[TestCase(12)]
        [TestCase(16)]
        public void Test21286(int docVersion)
        {
            Document doc = CreateDocumentWithChart();
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;

            doc.BuiltInDocumentProperties.Version = docVersion << 16;

            ChartSeries series = chart.Series[0];

            series.HasDataLabels = true;
            series.DataLabels.ShowValue = true;
            series.DataLabels.NumberFormat.FormatCode = "#,##0.00";

            series.DataLabels[1].ShowCategoryName = true;
            series.DataLabels[1].ShowValue = true;
            series.DataLabels[1].NumberFormat.FormatCode = "#,##0.000";

            series.DataLabels[2].NumberFormat.IsLinkedToSource = true;

            Assert.That(series.DataLabels.NumberFormat.FormatCode, Is.EqualTo("#,##0.00"));
            Assert.That(series.DataLabels[0].NumberFormat.FormatCode, Is.EqualTo("#,##0.00"));
            Assert.That(series.DataLabels[1].NumberFormat.FormatCode, Is.EqualTo("#,##0.000"));
            Assert.That(series.DataLabels.NumberFormat.IsLinkedToSource, Is.False);
            Assert.That(series.DataLabels[2].NumberFormat.IsLinkedToSource, Is.True);

            string fileName = string.Format(@"Model\Charts\Test20203Version{0}.docx", docVersion);
            TestUtil.Save(doc, fileName, null, true, GoldLevel.ExportOnly);
        }