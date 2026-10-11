[Test]
        public void TestDataLabelFontInNewChart()
        {
            // TODO: add testing of Word 2016 charts when they can be created in AW.

            Document doc = new Document();
            DocumentBuilder builder  = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Line, 432, 252);
            ChartSeries series = shape.Chart.Series[0];
            ChartDataLabelCollection labels = series.DataLabels;
            series.HasDataLabels = true;
            labels.ShowValue = true;

            Font font = labels.Font;
            Font font1 = labels[0].Font;

            CheckFont(font, "Calibri", 10, Color.Empty, Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            CheckFont(font1, "Calibri", 10, Color.Empty, Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            // Change font.

            ChangeFont(font, "Arial", 11, Color.DarkRed, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);

            ChangeFont(font1, "Times New Roman", 14, Color.Red, true, false,
                Underline.Double, 0, 0, false, true, false, true, RunVerticalAlignment.Subscript, 1049);

            labels[1].Font.Size = 9;

            // Check.

            CheckFont(font, "Arial", 11, Color.FromArgb(0x8b, 0, 0), Color.Empty, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);

            CheckFont(font1, "Times New Roman", 14, Color.FromArgb(0xff, 0, 0), Color.Empty, true, false,
                Underline.Double, 0, 0, false, true, false, true, RunVerticalAlignment.Subscript, 1049);

            CheckFont(labels[1].Font, "Arial", 9, Color.FromArgb(0x8b, 0, 0), Color.Empty, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);

            CheckFont(labels[2].Font, "Arial", 11, Color.FromArgb(0x8b, 0, 0), Color.Empty, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);
        }