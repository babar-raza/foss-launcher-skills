[Test]
        public void TestDataLabelCollectionFont()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestDataLabelFont.docx");

            // Test pre-Word 2016 chart.

            ChartSeries series1 = doc.FirstSection.Body.Shapes[0].Chart.Series[0];
            ChartDataLabelCollection labels1 = series1.DataLabels;
            Font font1 = labels1.Font;
            CheckFont(font1, "Verdana", 12, Color.FromArgb(99, 123, 156), Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            ChangeFont(font1, "Courier New", 14, Color.DarkRed, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1033);
            font1.HighlightColor = Color.Cyan;

            // Test Word 2016 chart.

            ChartSeries series2 = doc.FirstSection.Body.Shapes[1].Chart.Series[0];
            ChartDataLabelCollection labels2 = series2.DataLabels;
            Font font2 = labels2.Font;

            CheckFont(font2, "Verdana", 12, Color.FromArgb(89, 89, 89), Color.Empty, false, false,
                Underline.None, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);

            ChangeFont(font2, "Courier New", 14, Color.DarkRed, true, false,
                Underline.Double, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            font2.HighlightColor = Color.Cyan;

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestDataLabelCollectionFont.docx",
                UnifiedScenario.Docx2Docx | UnifiedScenario.ExportOnly);

            // Check results.

            series1 = doc.FirstSection.Body.Shapes[0].Chart.Series[0];
            labels1 = series1.DataLabels;
            font1 = labels1.Font;

            Color cyanColor = Color.FromArgb(0, 0xff, 0xff);

            CheckFont(font1, "Courier New", 14, Color.FromArgb(0x8b, 0, 0), cyanColor, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1033);

            CheckFont(labels1[0].Font, "Times New Roman", 12, Color.FromArgb(0, 128, 0), Color.Empty, false, true,
                Underline.Single, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);
            CheckFont(labels1[1].Font, "Courier New", 10, Color.FromArgb(0x8b, 0, 0), cyanColor, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1033);
            CheckFont(labels1[2].Font, "Arial", 18, Color.Empty, Color.Empty, false, false,
                Underline.None, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(labels1[3].Font, "Courier New", 14, Color.FromArgb(0x8b, 0, 0), cyanColor, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1033);
            CheckFont(labels1[4].Font, "Courier New", 14, Color.FromArgb(0x8b, 0, 0), cyanColor, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1033);
            CheckFont(labels1[5].Font, "Courier New", 8, Color.FromArgb(0, 0x80, 0), cyanColor, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Baseline, 1033);

            series2 = doc.FirstSection.Body.Shapes[1].Chart.Series[0];
            labels2 = series2.DataLabels;
            font2 = labels2.Font;

            CheckFont(font2, "Courier New", 14, Color.FromArgb(0x8b, 0, 0), cyanColor, true, false,
                Underline.Double, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1049);

            CheckFont(labels2[0].Font, "Times New Roman", 11, Color.FromArgb(0, 128, 0), cyanColor, false, true,
                Underline.Single, 10, 1, false, false, true, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(labels2[1].Font, "Courier New", 14, Color.FromArgb(0x8b, 0, 0), cyanColor, true, false,
                Underline.Double, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            CheckFont(labels2[2].Font, "Calibri", 10, Color.FromArgb(89, 89, 89), cyanColor, true, true,
                Underline.None, 10, 1, false, false, true, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(labels2[3].Font, "Courier New", 14, Color.FromArgb(0x8b, 0, 0), cyanColor, true, false,
                Underline.Double, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1049);

            // Test ClearFormatting.
            // After clearing formatting chart space font options are used for pre-Word 2016 charts.

            font1.ClearFormatting();
            font2.ClearFormatting();

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestDataLabelCollectionFontClearFormattin