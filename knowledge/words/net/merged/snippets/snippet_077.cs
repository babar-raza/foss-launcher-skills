[Test]
        public void TestLegendEntryFontInheritedProperties()
        {
            Document doc = TestUtil.Open(@"Model\Charts\Test23210.docx");
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;
            ChartLegendEntryCollection legendEntries = chart.Legend.LegendEntries;

            chart.Series.Add(
                "Series 5",
                new string[] { "Category1", "Category2", "Category3", "Category4" },
                new double[] { 7, 6, 5, 4 });

            Assert.That(legendEntries.Count, Is.EqualTo(9));

            Font font0 = legendEntries[0].Font;
            Font font2 = legendEntries[2].Font;
            Font font4 = legendEntries[4].Font;
            Font font8 = legendEntries[8].Font;

            CheckFont(font0, "Calibri", 8, Color.Empty, false, false, Underline.None);
            CheckFont(font2, "Calibri Light", 10, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font4, "Calibri", 10, Color.Empty, false, false, Underline.None);
            CheckFont(font8, "Calibri", 14, Color.Empty, false, false, Underline.None);

            // Change chart space properties to check that if a property is not defined directly and is not defined in
            // legend, it is taken from chart space properties.

            DmlRunProperties chartSpaceProperties = chart.ChartSpace.TxPr.RunPr;
            chartSpaceProperties.LatinFont = new DmlFont();
            chartSpaceProperties.LatinFont.TextTypeface = "Times New Roman";
            chartSpaceProperties.FontSize = new DmlTextPoints(1200);
            chartSpaceProperties.Italics = true;
            chartSpaceProperties.Underline = Underline.Double;
            chartSpaceProperties.Fill = new DmlSolidFill(DmlColor.CreateFromArgb(1, 0, 0, 0x8B));
            chart.ChartSpace.TxPr.FirstParagraph.Properties.HasDefaultRunProperties = true;

            CheckFont(font0, "Times New Roman", 8, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);
            CheckFont(font2, "Calibri Light", 12, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font4, "Times New Roman", 12, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);
            CheckFont(font8, "Times New Roman", 14, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestLegendEntryFontInheritedProperties.docx", null, false);
            chart = doc.FirstSection.Body.Shapes[0].Chart;
            legendEntries = chart.Legend.LegendEntries;
            font0 = legendEntries[0].Font;
            font2 = legendEntries[2].Font;
            font4 = legendEntries[4].Font;
            font8 = legendEntries[8].Font;

            CheckFont(font0, "Times New Roman", 8, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);
            CheckFont(font2, "Calibri Light", 12, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font4, "Times New Roman", 12, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);
            CheckFont(font8, "Times New Roman", 14, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);

            // Change legend properties to check that if a property is not defined directly, it is taken from legend.

            DmlRunProperties legendProperties = chart.Legend.TxPr.RunPr;
            legendProperties.LatinFont = new DmlFont();
            legendProperties.LatinFont.TextTypeface = "Arial";
            legendProperties.FontSize = new DmlTextPoints(800);
            legendProperties.Bold = true;
            legendProperties.Italics = false;
            legendProperties.Underline = Underline.None;
            chart.Legend.TxPr.FirstParagraph.Properties.HasDefaultRunProperties = true;

            CheckFont(font0, "Times New Roman", 8, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);
            CheckFont(font2, "Calibri Light", 12, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font4, "Arial", 8, Color.FromArgb(0xFF, 0, 0, 0x8B), true, false, Underline.None);
            CheckFont(font8, "Times New Roman", 14, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestLegendEntryFontInheritedProperties.docx", null, false);
            chart = doc.FirstSection.Body.Shapes[0].Chart;
            legendEntries = chart.Legend.LegendEntries;
            font0 = legendEntries[0].Font;
            font2 = legendEntries[2].Font;
            font4 = legendEntries[4].Font;
            font8 = legendEntries[8].Font;

            CheckFont(font0, "Times New Roman", 8, Color.FromArgb(0xFF, 0, 0, 0x8B), false, true, Underline.Double);
            CheckFont(font2, "Calibri Light", 12, Color.FromArgb(0xFF, 0, 0x80, 0), true, true