[Test]
        public void Test23353()
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

            chart.Series.RemoveAt(1);

            // The original document contained 4 series and 4 trendlines. One series and one trendline has been removed.
            Assert.That(legendEntries.Count, Is.EqualTo(6));

            font0 = legendEntries[0].Font;
            Font font1 = legendEntries[1].Font;
            Font font5 = legendEntries[5].Font;
            CheckFont(font0, "Calibri", 8, Color.Empty, false, false, Underline.None);
            CheckFont(font1, "Calibri Light", 10, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font5, "Calibri", 14, Color.Empty, false, false, Underline.None);

            doc = TestUtil.SaveOpen(doc, fileName, null, false);
            chart = doc.FirstSection.Body.Shapes[0].Chart;
            legendEntries = chart.Legend.LegendEntries;

            Assert.That(legendEntries.Count, Is.EqualTo(6));

            font0 = legendEntries[0].Font;
            font1 = legendEntries[1].Font;
            font5 = legendEntries[5].Font;
            CheckFont(font0, "Calibri", 8, Color.Empty, false, false, Underline.None);
            CheckFont(font1, "Calibri Light", 10, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font5, "Calibri", 14, Color.Empty, false, false, Underline.None);

            chart.Series.RemoveAt(0);

            // One series and two trendlines has been removed.
            Assert.That(legendEntries.Count, Is.EqualTo(3));

            font0 = legendEntries[0].Font;
            font2 = legendEntries[2].Font;
            CheckFont(font0, "Calibri Light", 10, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font2, "Calibri", 14, Color.Empty, false, false, Underline.None);

            chart.Series.Add(
                "Series 5",
                new string[] { "Category1", "Category2", "Category3", "Category4" },
                new double[] { 7, 6, 5, 4 });

            Assert.That(legendEntries.Count, Is.EqualTo(4));

            font0 = legendEntries[0].Font;
            font2 = legendEntries[2].Font; // Font of the added series.
            Font font3 = legendEntries[3].Font;
            CheckFont(font0, "Calibri Light", 10, Color.FromArgb(0xFF, 0, 0x80, 0), true, true, Underline.Single);
            CheckFont(font2, "Calibri", 10, Color.Empty, false, false, Underline.None);
            CheckFont(font3, "Calibri", 14, Color.Empty, false, false, Underline.None);
        }