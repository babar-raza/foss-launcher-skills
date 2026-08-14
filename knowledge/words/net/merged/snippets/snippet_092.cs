[Test]
        public void TestParetoChartSeriesType()
        {
            Document doc = TestUtil.Open(@"Model\Charts\Word2016Charts\Pareto.docx");
            Shape shape = doc.FirstSection.Body.Shapes[0];
            ChartSeriesCollection seriesCollection = shape.Chart.Series;

            Assert.That(seriesCollection.Count, Is.EqualTo(3));
            Assert.That(seriesCollection[0].SeriesType, Is.EqualTo(ChartSeriesType.ParetoLine));
            Assert.That(seriesCollection[1].SeriesType, Is.EqualTo(ChartSeriesType.Pareto));
            Assert.That(seriesCollection[2].SeriesType, Is.EqualTo(ChartSeriesType.ParetoLine));
        }