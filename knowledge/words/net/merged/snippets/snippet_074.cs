[Test]
        public void Test23210()
        {
            const string fileName = @"Model\Charts\Test23210.docx";
            Document doc = TestUtil.Open(fileName);
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;
            ChartLegendEntryCollection legendEntries = chart.Legend.LegendEntries;
            ChartSeriesCollection series = chart.Series;

            Assert.That(legendEntries.Count, Is.EqualTo(8));

            Assert.That(series[0].LegendEntry, Is.SameAs(legendEntries[0]));
            Assert.That(series[1].LegendEntry, Is.SameAs(legendEntries[1]));
            Assert.That(series[2].LegendEntry, Is.SameAs(legendEntries[2]));
            Assert.That(series[3].LegendEntry, Is.SameAs(legendEntries[3]));

            Assert.That(legendEntries[0].IsHidden, Is.False);
            Assert.That(legendEntries[6].IsHidden, Is.False);

            legendEntries[0].IsHidden = true;
            legendEntries[6].IsHidden = true;

            doc = TestUtil.SaveOpen(doc, fileName, null, false);
            chart = doc.FirstSection.Body.Shapes[0].Chart;
            legendEntries = chart.Legend.LegendEntries;

            Assert.That(chart.Legend.LegendEntries.Count, Is.EqualTo(8));
            Assert.That(legendEntries[0].IsHidden, Is.True);
            Assert.That(legendEntries[6].IsHidden, Is.True);
        }