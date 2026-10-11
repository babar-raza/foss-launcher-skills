[Test]
        public void TestLegendFontInNewChart()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape1 = builder.InsertChart(ChartType.Column, 432, 252);

            ChartLegend legend1 = shape1.Chart.Legend;
            Font font1 = legend1.Font;

            CheckFont(font1, "Calibri", 9, Color.FromArgb(0x59, 0x59, 0x59), false, false, Underline.None);

            font1.Name = "Times New Roman";
            font1.NameBi = "Courier New";
            font1.NameFarEast = "Arial";
            font1.NameOther = "Wingdings";
            font1.Size = 12;
            font1.Color = Color.DarkRed;
            font1.HighlightColor = Color.Cyan;
            font1.Bold = true;
            font1.Italic = false;
            font1.Underline = Underline.Single;
            font1.StrikeThrough = true;
            font1.SmallCaps = true;
            font1.VerticalAlignment = RunVerticalAlignment.Subscript;
            font1.LocaleId = 1033;
            font1.Kerning = 3;
            font1.Spacing = 2;

            builder.InsertParagraph();

            Shape shape2 = builder.InsertChart(ChartType.Column, 432, 252);

            ChartLegend legend2 = shape2.Chart.Legend;
            Font font2 = legend2.Font;
            font2.Size = 15;
            font2.Bold = true;

            font2.Fill.TwoColorGradient(Color.Blue, Color.Orange, GradientStyle.DiagonalDown, GradientVariant.Variant2);

            Assert.That(font2.Color, Is.EqualTo(Color.Empty));
            Assert.That(font2.Fill.ForeColor, Is.EqualTo(Color.FromArgb(0, 0, 0xff)));
            Assert.That(font2.Fill.BackColor, Is.EqualTo(Color.FromArgb(0xff, 0xa5, 0)));

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestLegendFontInNewChart.docx", null, false);
            legend1 = doc.FirstSection.Body.Shapes[0].Chart.Legend;
            font1 = legend1.Font;

            CheckFont(font1, "Times New Roman", 12, Color.FromArgb(0xFF, 0x8B, 0, 0), true, false, Underline.Single);

            Assert.That(font1.Kerning, Is.EqualTo(3));
            Assert.That(font1.Spacing, Is.EqualTo(2));
            Assert.That(font1.NameBi, Is.EqualTo("Courier New"));
            Assert.That(font1.NameFarEast, Is.EqualTo("Arial"));
            Assert.That(font1.NameOther, Is.EqualTo("Wingdings"));
            Assert.That(font1.DoubleStrikeThrough, Is.False);
            Assert.That(font1.StrikeThrough, Is.True);
            Assert.That(font1.AllCaps, Is.False);
            Assert.That(font1.SmallCaps, Is.True);
            Assert.That(font1.VerticalAlignment, Is.EqualTo(RunVerticalAlignment.Subscript));
            Assert.That(font1.HighlightColor, Is.EqualTo(Color.FromArgb(0xFF, 0, 0xFF, 0xFF)));
            Assert.That(font1.LocaleId, Is.EqualTo(1033));

            legend2 = doc.FirstSection.Body.Shapes[1].Chart.Legend;
            font2 = legend2.Font;

            CheckFont(font2, "Calibri", 15, Color.Empty, true, false, Underline.None);

            Assert.That(font2.Fill.ForeColor, Is.EqualTo(Color.FromArgb(0, 0, 0xff)));
            Assert.That(font2.Fill.BackColor, Is.EqualTo(Color.FromArgb(0xff, 0xa5, 0)));
        }