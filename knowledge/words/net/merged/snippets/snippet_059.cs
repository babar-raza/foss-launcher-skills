[TestCase((int)MsWordVersionCore.Word2007)]
        [TestCase((int)MsWordVersionCore.Word2010)]
        public void TestInvertIfNegative(int documentVersion)
        {
            Document doc = new Document();
            doc.BuiltInDocumentProperties.Version =
                (doc.BuiltInDocumentProperties.Version & 0xff) + (documentVersion << 16);

            DocumentBuilder builder = new DocumentBuilder(doc);
            builder.InsertChart(ChartType.Bar, 432, 252);

            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;

            ChartSeries series1 = chart.Series[0];
            // Define some formatting.
            series1.DataPoints[0].Format.Fill.Solid(Color.Green);
            series1.DataPoints[1].Format.Fill.Solid(Color.Cyan);

            series1.DefaultDataPoint.PointPr.RemoveProperty(DmlChartDataPointAttr.InvertIfNegative);

            MsWordVersionCore version = (MsWordVersionCore)documentVersion;
            bool expectedDefaultValue = (version > MsWordVersionCore.Word2007);
            CheckInvertIfNegative(series1, expectedDefaultValue, expectedDefaultValue, expectedDefaultValue);

            series1.InvertIfNegative = true;
            CheckInvertIfNegative(series1, true, true, true);

            series1.DataPoints[1].InvertIfNegative = false;
            CheckInvertIfNegative(series1, true, true, false);

            ChartSeries series2 = chart.Series[1];
            // Define some formatting.
            series2.DataPoints[0].Format.Fill.Solid(Color.Green);
            series2.DataPoints[1].Format.Fill.Solid(Color.Cyan);

            series2.InvertIfNegative = false;
            CheckInvertIfNegative(series2, false, false, false);

            series2.DataPoints[1].InvertIfNegative = true;
            CheckInvertIfNegative(series2, false, false, true);

            doc = TestUtil.SaveOpen(doc, string.Format(@"Model\Charts\TestInvertIfNegative{0}", version.ToString()),
                UnifiedScenario.Docx2Docx | UnifiedScenario.ExportOnly);

            chart = doc.FirstSection.Body.Shapes[0].Chart;

            series1 = chart.Series[0];
            CheckInvertIfNegative(series1, true, true, false);

            series2 = chart.Series[1];
            CheckInvertIfNegative(series2, false, false, true);
        }