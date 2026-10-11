[Test]
        public void TestFontInNewChart()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Line, 432, 252);
            ChartDataTable dataTable = shape.Chart.DataTable;

            Assert.That(dataTable.Show, Is.False);
            dataTable.Show = true;

            Font font = dataTable.Font;

            CheckFont(font, "Calibri", 9, Color.FromArgb(0x59, 0x59, 0x59), Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            // Change font.

            ChangeFont(font, "Arial", 12, Color.DarkRed, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);

            // Check.

            CheckFont(font, "Arial", 12, DrColor.DarkRed.ToNativeColor(), Color.Empty, false, true,
                Underline.Single, 10, 1, true, false, true, false, RunVerticalAlignment.Superscript, 1033);
        }