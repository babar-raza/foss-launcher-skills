[Test]
        public void TestSupportedFontProperties()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);

            ChartSeries series = shape.Chart.Series[0];
            Font font = series.LegendEntry.Font;

            font.Name = "Arial";
            font.NameAscii = "Arial";
            font.NameBi = "Times New Roman";
            font.NameFarEast = "Calibri";
            font.NameOther = "Windings";
            font.ThemeFont = ThemeFont.None;
            font.ThemeFontAscii = ThemeFont.None;
            font.ThemeFontBi = ThemeFont.None;
            font.ThemeFontFarEast = ThemeFont.None;
            font.ThemeFontOther = ThemeFont.None;
            font.Size = 12;
            font.SizeBi = 12;
            font.Bold = false;
            font.BoldBi = false;
            font.Italic = true;
            font.ItalicBi = true;
            font.Color = Color.Blue;
            font.StrikeThrough = false;
            font.DoubleStrikeThrough = true;
            font.Superscript = false;
            font.Subscript = true;
            font.SmallCaps = false;
            font.AllCaps = false;
            font.Underline = Underline.None;
            font.Spacing = 1;
            font.Kerning = 1;
            font.HighlightColor = Color.Yellow;
            font.LocaleId = 0x1409;
            font.LocaleIdBi = 0x1409;
            font.LocaleIdFarEast = 0x1409;

            font.Fill.Solid(Color.Blue);
            font.Border.LineStyle = LineStyle.None;

            CheckFont(font, "Arial", 12, Color.FromArgb(0, 0, 0xff), false, true, Underline.None);
            Assert.That(font.NameAscii, Is.EqualTo("Arial"));
            Assert.That(font.NameBi, Is.EqualTo("Times New Roman"));
            Assert.That(font.NameFarEast, Is.EqualTo("Calibri"));
            Assert.That(font.NameOther, Is.EqualTo("Windings"));
            Assert.That(font.ThemeFont, Is.EqualTo(ThemeFont.None));
            Assert.That(font.ThemeFontAscii, Is.EqualTo(ThemeFont.None));
            Assert.That(font.ThemeFontBi, Is.EqualTo(ThemeFont.None));
            Assert.That(font.ThemeFontFarEast, Is.EqualTo(ThemeFont.None));
            Assert.That(font.ThemeFontOther, Is.EqualTo(ThemeFont.None));
            Assert.That(font.SizeBi, Is.EqualTo(12));
            Assert.That(font.BoldBi, Is.False);
            Assert.That(font.ItalicBi, Is.True);
            Assert.That(font.StrikeThrough, Is.False);
            Assert.That(font.DoubleStrikeThrough, Is.True);
            Assert.That(font.Superscript, Is.False);
            Assert.That(font.Subscript, Is.True);
            Assert.That(font.SmallCaps, Is.False);
            Assert.That(font.AllCaps, Is.False);
            Assert.That(font.Spacing, Is.EqualTo(1));
            Assert.That(font.Kerning, Is.EqualTo(1));
            Assert.That(font.HighlightColor, Is.EqualTo(Color.FromArgb(0xff, 0xff, 0)));
            // DML has only one locale Id property.
            // Font.LocaleId/LocaleIdBi/LocaleIdFarEast refer to the same DML property.
            Assert.That(font.LocaleId, Is.EqualTo(0x1409));
            Assert.That(font.LocaleIdBi, Is.EqualTo(0x1409));
            Assert.That(font.LocaleIdFarEast, Is.EqualTo(0x1409));
            // FOSS: font.LineSpacing assertion removed - it now reflects the last-resort font
            // (font-specific metrics were removed with the font substitution engine).

            // Readonly properties and method:
            Assert.That(font.HasDmlEffect(TextDmlEffect.Glow), Is.False);
            Assert.That(font.Fill.FillType, Is.EqualTo(FillType.Solid));
            Assert.That(font.AutoColor, Is.EqualTo(Color.FromArgb(0, 0, 0xff)));
            // Now a new instance of Border and Shading are returned when accessing the corresponding Font properties.
            Assert.That(font.Border.LineStyle, Is.EqualTo(LineStyle.None));
            Assert.That(font.Shading.BackgroundPatternColor, Is.EqualTo(Color.Empty));

            // Currently unsupported properties:
            Assert.That(font.ThemeColor, Is.EqualTo(ThemeColor.None));
            Assert.That(font.TintAndShade, Is.EqualTo(0));
            Assert.That(font.Shadow, Is.False);
            Assert.That(font.Outline, Is.False);
            Assert.That(font.Emboss, Is.False);
            Assert.That(font.Engrave, Is.False);
            Assert.That(font.Hidden, Is.False);
            Assert.That(font.UnderlineColor, Is.EqualTo(Color.Empty));
            Assert.That(font.Scaling, Is.EqualTo(100));
            Assert.That(font.Position, Is.EqualTo(0));
            Assert.That(font.TextEffect, Is.EqualTo(TextEffect.None));
            Assert.That(font.Bidi, Is.False);
            Assert.That(font.ComplexScript, Is.False);
            Assert.That(font.NoProofing, Is.False