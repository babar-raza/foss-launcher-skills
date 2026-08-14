[Test]
        public void TestDataLabelFont()
        {
            const string fileName = @"Model\Charts\TestDataLabelFont";
            Document doc = TestUtil.Open(fileName, LoadFormat.Docx);

            // Test pre-Word 2016 chart.

            ChartSeries series1 = doc.FirstSection.Body.Shapes[0].Chart.Series[0];
            ChartDataLabelCollection labels1 = series1.DataLabels;

            Assert.That(labels1.Count, Is.EqualTo(6));

            // Label with index 0 has txPr element with Times New Roman italic font.
            Font font1 = labels1[0].Font;
            // Label with index 1 has tx element with changed font size and bold state for the first run (field).
            Font font2 = labels1[1].Font;
            // Label with index 2 has tx, txPr and spPr elements.
            Font font3 = labels1[2].Font;
            // Non-materialized label.
            Font font4 = labels1[3].Font;
            // Non-materialized label.
            Font font5 = labels1[4].Font;
            // Label with index 5 has tx element with Verdana 8pt bold font.
            Font font6 = labels1[5].Font;

            CheckFont(font1, "Times New Roman", 12, Color.FromArgb(0, 128, 0), Color.Empty, false, true,
                Underline.Single, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);
            // Font is taken from the first run.
            CheckFont(font2, "Verdana", 10, Color.FromArgb(99, 123, 156), Color.Empty, true, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(font3, "Arial", 18, Color.Empty, Color.Empty, false, false,
                Underline.None, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(font4, "Verdana", 12, Color.FromArgb(99, 123, 156), Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);
            CheckFont(font5, "Verdana", 12, Color.FromArgb(99, 123, 156), Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);
            CheckFont(font6, "Verdana", 8, Color.FromArgb(0, 0x80, 0), Color.Empty, true, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);

            ChangeFont(font1, "Courier New", 14, Color.DarkRed, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1033);
            font1.HighlightColor = Color.Cyan;

            ChangeFont(font2, "Times New Roman", 12, Color.Green, false, true,
                Underline.Single, 12, 4, false, true, false, true, RunVerticalAlignment.Subscript, 1049);
            ChangeFont(font3, "Courier New", 10, Color.DarkBlue, true, true,
                Underline.Dotted, 2, 2, false, true, true, false, RunVerticalAlignment.Subscript, 1049);
            ChangeFont(font4, "Arial", 10, Color.Brown, false, false,
                Underline.Dash, 5, 1, true, false, false, true, RunVerticalAlignment.Superscript, 1049);

            font5.NameAscii = "Arial";

            font6.ClearFormatting();

            // Test Word 2016 chart.

            ChartSeries series2 = doc.FirstSection.Body.Shapes[1].Chart.Series[0];
            ChartDataLabelCollection labels2 = series2.DataLabels;

            Assert.That(labels2.Count, Is.EqualTo(8));

            // Label with index 0 has txPr element with Times New Roman italic 12pt font.
            font1 = labels2[0].Font;
            // Non-materialized label.
            font2 = labels2[1].Font;
            // Label with index 2 has txPr element with Calibri bold font.
            font3 = labels2[2].Font;
            // Label with index 3 has spPr element only.
            font4 = labels2[3].Font;

            CheckFont(font1, "Times New Roman", 11, Color.FromArgb(0, 128, 0), Color.Empty, false, true,
                Underline.Single, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(font2, "Verdana", 12, Color.FromArgb(89, 89, 89), Color.Empty, false, false,
                Underline.None, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(font3, "Calibri", 10, Color.FromArgb(89, 89, 89), Color.Empty, true, true,
                Underline.None, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);
            CheckFont(font4, "Verdana", 12, Color.FromArgb(89, 89, 89), Color.Empty, false, false,
                Underline.None, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1033);

            ChangeFont(font1, "Courier New", 14, Color.DarkRed, true, false,
                Underline.Double, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            font1.