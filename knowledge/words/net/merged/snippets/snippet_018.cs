[TestCase(ChartType.Line)] // pre-Word 2016 chart
        [TestCase(ChartType.Waterfall)] // Word 2016 chart
        public void TestTickLabelsFontInNewChart(ChartType chartType)
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(chartType, 432, 252);
            Chart chart = shape.Chart;

            Font xFont = chart.AxisX.TickLabels.Font;
            Font yFont = chart.AxisY.TickLabels.Font;

            int defaultKerning = chart.ChartSpace.IsChartEx ? 0 : 12;

            CheckFont(xFont, "Calibri", 9, Color.FromArgb(89, 89, 89), Color.Empty, false, false, Underline.None,
                defaultKerning, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            CheckFont(yFont, "Calibri", 9, Color.FromArgb(89, 89, 89), Color.Empty, false, false, Underline.None,
                defaultKerning, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            // Change font.

            ChangeFont(xFont, "Arial", 11, Color.DarkRed, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);

            ChangeFont(yFont, "Times New Roman", 14, Color.Red, true, false,
                Underline.Double, 0, 0, false, true, false, true, RunVerticalAlignment.Subscript, 1049);

            // Check.

            CheckFont(xFont, "Arial", 11, Color.FromArgb(139, 0, 0), Color.Empty, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);

            CheckFont(yFont, "Times New Roman", 14, Color.FromArgb(255, 0, 0), Color.Empty, true, false,
                Underline.Double, 0, 0, false, true, false, true, RunVerticalAlignment.Subscript, 1049);
        }