[TestCase("Test23210", "Calibri", 10, 0u)]
        // Font is defined in legend (pre Word 2016 chart).
        [TestCase("TestLegendEntriesOrderStacked", "Calibri", 9, 0xff595959u)]
        // Font is defined in chart space (pre Word 2016 chart).
        [TestCase("TestChartSpaceFont", "Arial", 12, 0xff2F5496u)]
        // Chart space is not used in Word 2016 charts to get legend font properties.
        // Font is not defined in legend (Word 2016 chart).
        [TestCase(@"Word2016Charts\Pareto", "Calibri", 9, 0xff595959u)]
        // Font is defined in legend (Word 2016 chart).
        [TestCase(@"Word2016Charts\TestLegendFont", "Courier New", 11, 0xff6ca644u)]
        public void TestLegendFont(string fileName, string expectedName, int expectedSize, uint expectedColor)
        {
            Document doc = TestUtil.Open(string.Format(@"Model\Charts\{0}.docx", fileName));
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;
            ChartLegend legend = chart.Legend;
            Font font = legend.Font;

            Color color = (expectedColor == 0) ? Color.Empty : Color.FromArgb(unchecked((int)expectedColor));

            CheckFont(font, expectedName, expectedSize, color, false, false, Underline.None);

            int expectedKerning = chart.ChartSpace.IsChartEx ? 0 : 12;
            Assert.That(font.Kerning, Is.EqualTo(expectedKerning));
            Assert.That(font.Spacing, Is.EqualTo(0));
            Assert.That(font.DoubleStrikeThrough, Is.False);
            Assert.That(font.StrikeThrough, Is.False);
            Assert.That(font.AllCaps, Is.False);
            Assert.That(font.SmallCaps, Is.False);
            Assert.That(font.VerticalAlignment, Is.EqualTo(RunVerticalAlignment.Baseline));
            Assert.That(font.HighlightColor, Is.EqualTo(Color.Empty));

            font.Name = "Times New Roman";
            font.NameBi = "Courier New";
            font.NameFarEast = "Arial";
            font.NameOther = "Wingdings";
            font.Size = 14;
            font.Color = Color.DarkRed;
            font.HighlightColor = Color.Cyan;
            font.Bold = false;
            font.Italic = true;
            font.Underline = Underline.None;
            font.DoubleStrikeThrough = true;
            font.AllCaps = true;
            font.VerticalAlignment = RunVerticalAlignment.Superscript;
            font.LocaleId = 1033;
            font.Kerning = 10;
            font.Spacing = 3;

            doc = TestUtil.SaveOpen(doc, string.Format(@"Model\Charts\{0}LegendFont.docx", fileName), null, false);
            legend = doc.FirstSection.Body.Shapes[0].Chart.Legend;
            font = legend.Font;

            CheckFont(font, "Times New Roman", 14, Color.FromArgb(0xFF, 0x8B, 0, 0), false, true, Underline.None);

            Assert.That(font.Kerning, Is.EqualTo(10));
            Assert.That(font.Spacing, Is.EqualTo(3));
            Assert.That(font.NameBi, Is.EqualTo("Courier New"));
            Assert.That(font.NameFarEast, Is.EqualTo("Arial"));
            Assert.That(font.NameOther, Is.EqualTo("Wingdings"));
            Assert.That(font.DoubleStrikeThrough, Is.True);
            Assert.That(font.StrikeThrough, Is.False);
            Assert.That(font.AllCaps, Is.True);
            Assert.That(font.SmallCaps, Is.False);
            Assert.That(font.VerticalAlignment, Is.EqualTo(RunVerticalAlignment.Superscript));
            Assert.That(font.HighlightColor, Is.EqualTo(Color.FromArgb(0xFF, 0, 0xFF, 0xFF)));
            Assert.That(font.LocaleId, Is.EqualTo(1033));
        }