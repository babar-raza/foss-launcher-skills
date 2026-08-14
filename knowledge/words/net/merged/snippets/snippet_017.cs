[Test]
        public void TestTickLabelsFont()
        {
            const string fileName = @"Model\Charts\TestTickLabelsFont";
            Document doc = TestUtil.Open(fileName, LoadFormat.Docx);

            // Clone the first and second charts, and a paragraph between them.
            Body body = doc.FirstSection.Body;
            Paragraph para1 = body.Paragraphs[0];
            body.AppendChild(para1.Clone(true));
            Paragraph para2 = body.Paragraphs[1];
            body.AppendChild(para2.Clone(true));
            Paragraph para3 = body.Paragraphs[2];
            body.AppendChild(para3.Clone(true));

            // Pre-Word 2016 chart.

            Chart chart1 = body.Shapes[0].Chart;

            // X axis font is changed.
            Font xFont1 = chart1.AxisX.TickLabels.Font;
            // Y axis font is taken from chart space.
            Font yFont1 = chart1.AxisY.TickLabels.Font;

            CheckFont(xFont1, "Calibri", 9, Color.FromArgb(89, 89, 89), Color.Empty, false, false,
                Underline.None, 12, 0.2, false, false, false, false, RunVerticalAlignment.Baseline, 1024);
            CheckFont(yFont1, "Times New Roman", 14, Color.Empty, Color.Empty, false, true,
                Underline.Single, 9, 0, false, false, false, false, RunVerticalAlignment.Superscript, 1024);

            ChangeFont(xFont1, "Courier New", 11, Color.DarkRed, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            xFont1.HighlightColor = Color.Cyan;

            ChangeFont(yFont1, "Verdana", 12, Color.Green, true, false,
                Underline.None, 12, 4, false, true, false, true, RunVerticalAlignment.Baseline, 1049);

            // Word 2016 chart.

            Chart chart2 = body.Shapes[1].Chart;

            // X axis font is changed.
            Font xFont2 = chart2.AxisX.TickLabels.Font;
            // Default format is used for Y axis font.
            Font yFont2 = chart2.AxisY.TickLabels.Font;

            CheckFont(xFont2, "Calibri", 8, Color.FromArgb(68, 114, 196), Color.Empty, false, false,
                Underline.Dotted, 0, 0.2, false, false, true, false, RunVerticalAlignment.Baseline, 1024);
            CheckFont(yFont2, "Calibri", 9, Color.FromArgb(89, 89, 89), Color.Empty, false, false,
                Underline.None, 0, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            ChangeFont(xFont2, "Courier New", 10, Color.DarkRed, true, false,
                Underline.Double, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            xFont2.HighlightColor = Color.Cyan;

            ChangeFont(yFont2, "Times New Roman", 10, Color.Green, false, true,
                Underline.Single, 12, 2, false, true, false, true, RunVerticalAlignment.Subscript, 1049);

            // Pre-Word 2016 chart.

            Chart chart3 = body.Shapes[2].Chart;

            // Default font format is used for X axis.
            Font xFont3 = chart3.AxisX.TickLabels.Font;

            CheckFont(xFont3, "Calibri", 10, Color.Empty, Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            // Pre-Word 2016 chart.

            Chart chart4 = body.Shapes[3].Chart;

            Font xFont4 = chart4.AxisX.TickLabels.Font;
            CheckFont(xFont4, "Calibri", 9, Color.FromArgb(89, 89, 89), Color.Empty, false, false,
                Underline.None, 12, 0.2, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            xFont4.ClearFormatting();

            // Word 2016 chart.

            Chart chart5 = body.Shapes[4].Chart;

            Font xFont5 = chart5.AxisX.TickLabels.Font;
            CheckFont(xFont5, "Calibri", 8, Color.FromArgb(68, 114, 196), Color.Empty, false, false,
                Underline.Dotted, 0, 0.2, false, false, true, false, RunVerticalAlignment.Baseline, 1024);

            xFont5.ClearFormatting();

            doc = TestUtil.SaveOpen(doc, fileName, UnifiedScenario.Docx2Docx | UnifiedScenario.ExportOnly);
            body = doc.FirstSection.Body;
            chart1 = body.Shapes[0].Chart;
            chart2 = body.Shapes[1].Chart;
            chart3 = body.Shapes[2].Chart;
            chart4 = body.Shapes[3].Chart;
            chart5 = body.Shapes[4].Chart;

            // Check results.

            CheckFont(chart1.AxisX.TickLabels.Font, "Courier New", 11, Color.FromArgb(139, 0, 0),
                Color.FromArgb(0, 255, 255),
                true, false, Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            CheckFont(chart1.AxisY.TickLabels.Font, "Verdana", 12, Color.FromArgb(0, 128, 0), Color.Empty,
                true, false, Underline.None, 12, 4, false, true, false, true, RunVerticalAlignment.Basel