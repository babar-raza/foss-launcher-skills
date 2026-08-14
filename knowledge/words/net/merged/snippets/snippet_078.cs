[Test]
        public void Test23543()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);

            ChartSeries series = shape.Chart.Series[0];
            Font font = series.LegendEntry.Font;

            CheckFont(font, "Calibri", 9, Color.FromArgb(89, 89, 89), false, false, Underline.None);

            shape.Chart.Legend.TxPr.RunPr.Italics = true;
            shape.Chart.Legend.TxPr.RunPr.Underline = Underline.Dotted;
            CheckFont(font, "Calibri", 9, Color.FromArgb(89, 89, 89), false, true, Underline.Dotted);

            font.Size = 12;

            CheckFont(font, "Calibri", 12, Color.FromArgb(89, 89, 89), false, true, Underline.Dotted);

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\Test23543",
                UnifiedScenario.Docx2Docx | UnifiedScenario.ExportOnly);

            series = doc.FirstSection.Body.Shapes[0].Chart.Series[0];
            font = series.LegendEntry.Font;

            CheckFont(font, "Calibri", 12, Color.FromArgb(89, 89, 89), false, true, Underline.Dotted);

            font.ClearFormatting();
            CheckFont(font, "Calibri", 9, Color.FromArgb(89, 89, 89), false, true, Underline.Dotted);

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\Test23543ClearFormat",
                UnifiedScenario.Docx2Docx | UnifiedScenario.ExportOnly);

            series = doc.FirstSection.Body.Shapes[0].Chart.Series[0];
            font = series.LegendEntry.Font;
            CheckFont(font, "Calibri", 9, Color.FromArgb(89, 89, 89), false, true, Underline.Dotted);
        }