[Test]
        public void TestCopyingFormat()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestCopyingDataPointFormat.docx");
            ChartSeries series1 = doc.FirstSection.Body.Shapes[0].Chart.Series[0];
            ChartDataPointCollection dataPoints1 = series1.DataPoints;
            ChartSeries series2 = doc.FirstSection.Body.Shapes[1].Chart.Series[0];
            ChartDataPointCollection dataPoints2 = series2.DataPoints;

            Assert.That(dataPoints1.HasDefaultFormat(1), Is.False);
            Assert.That(dataPoints1.HasDefaultFormat(2), Is.True);
            Assert.That(dataPoints2.HasDefaultFormat(1), Is.False);
            Assert.That(dataPoints2.HasDefaultFormat(2), Is.True);

            dataPoints1.CopyFormat(1, 2);
            dataPoints2.CopyFormat(1, 2);

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestCopyingDataPointFormatForItem.docx");

            series1.CopyFormatFrom(1);
            series2.CopyFormatFrom(1);

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestCopyingDataPointFormatForCollection.docx");
        }