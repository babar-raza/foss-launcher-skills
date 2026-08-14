[Test]
        public void TestFontFill()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);

            ChartLegend legend = shape.Chart.Legend;
            DmlRunProperties legendRunProperties = legend.TxPr.RunPr;
            Font font1 = legend.LegendEntries[0].Font;
            Font font2 = legend.LegendEntries[1].Font;

            // Reset legend fill.
            legendRunProperties.Remove(DmlRunPropertiesIds.Fill);

            font1.Fill.Solid(Color.Blue);

            Assert.That(font1.Color, Is.EqualTo(Color.FromArgb(0, 0, 0xff)));
            Assert.That(font1.Fill.ForeColor, Is.EqualTo(Color.FromArgb(0, 0, 0xff)));

            legendRunProperties.Fill = new DmlSolidFill(DmlColor.CreateFromArgb(1, 0xff, 0, 0));

            Assert.That(font1.Color, Is.EqualTo(Color.FromArgb(0, 0, 0xff)));
            Assert.That(font1.Fill.ForeColor, Is.EqualTo(Color.FromArgb(0, 0, 0xff)));
            Assert.That(font2.Color, Is.EqualTo(Color.FromArgb(0xff, 0, 0)));
            Assert.That(font2.Fill.ForeColor, Is.EqualTo(Color.FromArgb(0xff, 0, 0)));
            Assert.That(legendRunProperties.Fill.ColorInternal.ToNativeColor(), Is.EqualTo(Color.FromArgb(0xff, 0, 0)));

            font2.Color = Color.Green;

            Assert.That(font2.Color, Is.EqualTo(Color.FromArgb(0, 0x80, 0)));
            Assert.That(font2.Fill.ForeColor, Is.EqualTo(Color.FromArgb(0, 0x80, 0)));
            Assert.That(legendRunProperties.Fill.ColorInternal.ToNativeColor(), Is.EqualTo(Color.FromArgb(0xff, 0, 0)));

            TestUtil.Save(doc, @"Model\Charts\TestFontFill.docx", null, true);
        }