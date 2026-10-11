[Test]
        public void TestLegendEntryFont()
        {
            const string fileName = @"Model\Charts\Test23210.docx";
            Document doc = TestUtil.Open(fileName);
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;
            ChartLegendEntryCollection legendEntries = chart.Legend.LegendEntries;

            Assert.That(legendEntries.Count, Is.EqualTo(8));

            Font font0 = legendEntries[0].Font;
            Font font2 = legendEntries[2].Font;
            Font font7 = legendEntries[7].Font;
            CheckFont(font0, "Calibri", 8, Color.Empty, false, false, Underline.None);
            CheckFont(font2, "Calibri Light", 10, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font7, "Calibri", 14, Color.Empty, false, false, Underline.None);

            Assert.That(font2.Kerning, Is.EqualTo(12));
            Assert.That(font2.Spacing, Is.EqualTo(0));
            Assert.That(font2.NameBi, Is.EqualTo("Calibri Light"));
            Assert.That(font2.DoubleStrikeThrough, Is.EqualTo(false));
            Assert.That(font2.StrikeThrough, Is.EqualTo(false));
            Assert.That(font2.AllCaps, Is.EqualTo(false));
            Assert.That(font2.SmallCaps, Is.EqualTo(false));
            Assert.That(font2.VerticalAlignment, Is.EqualTo(RunVerticalAlignment.Baseline));
            Assert.That(font2.HighlightColor, Is.EqualTo(Color.Empty));
            Assert.That(font2.LocaleId, Is.EqualTo(1024));

            font2.Name = "Times New Roman";
            font2.NameBi = "Courier New";
            font2.NameFarEast = "Arial";
            font2.NameOther = "Wingdings";
            font2.Size = 14;
            font2.Color = Color.DarkRed;
            font2.HighlightColor = Color.Cyan;
            font2.Bold = false;
            font2.Italic = false;
            font2.Underline = Underline.None;
            font2.DoubleStrikeThrough = true;
            font2.AllCaps = true;
            font2.VerticalAlignment = RunVerticalAlignment.Superscript;
            font2.LocaleId = 1033;
            font2.Kerning = 10;
            font2.Spacing = 3;

            font7.Bold = true;
            font7.Italic = true;
            font7.StrikeThrough = true;
            font7.SmallCaps = true;

            doc = TestUtil.SaveOpen(doc, fileName, null, false);
            chart = doc.FirstSection.Body.Shapes[0].Chart;
            legendEntries = chart.Legend.LegendEntries;

            Assert.That(legendEntries.Count, Is.EqualTo(8));

            font2 = legendEntries[2].Font;
            font7 = legendEntries[7].Font;

            CheckFont(font2, "Times New Roman", 14, Color.FromArgb(0xFF, 0x8B, 0, 0), false, false, Underline.None);
            CheckFont(font7, "Calibri", 14, Color.Empty, true, true, Underline.None);

            Assert.That(font2.Kerning, Is.EqualTo(10));
            Assert.That(font2.Spacing, Is.EqualTo(3));
            Assert.That(font2.NameBi, Is.EqualTo("Courier New"));
            Assert.That(font2.NameFarEast, Is.EqualTo("Arial"));
            Assert.That(font2.NameOther, Is.EqualTo("Wingdings"));
            Assert.That(font2.DoubleStrikeThrough, Is.EqualTo(true));
            Assert.That(font2.StrikeThrough, Is.EqualTo(false));
            Assert.That(font2.AllCaps, Is.EqualTo(true));
            Assert.That(font2.SmallCaps, Is.EqualTo(false));
            Assert.That(font2.VerticalAlignment, Is.EqualTo(RunVerticalAlignment.Superscript));
            Assert.That(font2.HighlightColor, Is.EqualTo(Color.FromArgb(0xFF, 0, 0xFF, 0xFF)));
            Assert.That(font2.LocaleId, Is.EqualTo(1033));

            Assert.That(font7.DoubleStrikeThrough, Is.EqualTo(false));
            Assert.That(font7.StrikeThrough, Is.EqualTo(true));
            Assert.That(font7.AllCaps, Is.EqualTo(false));
            Assert.That(font7.SmallCaps, Is.EqualTo(true));
        }