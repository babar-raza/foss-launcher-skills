[Test]
        public void TestInheritedPropertyValues()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Line, 432, 252);
            Chart chart = shape.Chart;

            chart.Series.Clear();
            ChartSeries series = chart.Series.Add("AW Series 1",
                new DateTime[] { new DateTime(2002, 01, 01), new DateTime(2002, 06, 01), new DateTime(2002, 07, 01),
                    new DateTime(2002, 08, 01), new DateTime(2002, 09, 01) },
                new double[] { 640, 120, 280, 120, 150 });

            Assert.That(((IChartDataPoint)series).Marker.Symbol, Is.EqualTo(MarkerSymbol.None));

            ChartDataPoint point1 = series.DataPoints[1];
            point1.InvertIfNegative = true;
            point1.Marker.Size = 12;

            Assert.That(point1.Marker.Symbol, Is.EqualTo(MarkerSymbol.None));

            ((IChartDataPoint)series).Marker.Symbol = MarkerSymbol.Diamond;
            ((IChartDataPoint)series).Marker.Size = 24;

            Assert.That(point1.Marker.Symbol, Is.EqualTo(MarkerSymbol.Diamond));
            Assert.That(point1.Marker.MarkerPr.GetDirectProperty(DmlChartMarkerAttr.Symbol), Is.Null);

            ChartDataPoint point2 = series.DataPoints[2];
            point2.InvertIfNegative = true;
            Assert.That(point2.Marker.Symbol, Is.EqualTo(MarkerSymbol.Diamond));

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestInheritedPropertyValues.docx", null, false);

            chart = doc.FirstSection.Body.Shapes[0].Chart;
            series = chart.Series[0];
            point1 = series.DataPoints[1];

            Assert.That(point1.Marker.Symbol, Is.EqualTo(MarkerSymbol.Diamond));
            Assert.That(point1.Marker.MarkerPr.GetDirectProperty(DmlChartMarkerAttr.Symbol), Is.Null);
            Assert.That(point1.Marker.Size, Is.EqualTo(12));
            Assert.That(point1.InvertIfNegative, Is.True);

            point2 = series.DataPoints[2];
            Assert.That(point2.InvertIfNegative, Is.True);
            Assert.That(point2.Marker.Symbol, Is.EqualTo(MarkerSymbol.Diamond));
        }