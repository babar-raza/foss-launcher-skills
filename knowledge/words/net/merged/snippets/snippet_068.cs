[TestCase(@"Word2016Charts\BoxWhisker.docx")]
        [TestCase("TestScatterChart.docx")]
        [ExpectedException(typeof(InvalidOperationException),
            ExpectedMessage = "This chart type does not support a data table.")]
        public void TestShowingDataTableInNonSupportedChart(string relativeFileName)
        {
            Document doc = TestUtil.Open(@"Model\Charts\" + relativeFileName);
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;

            // This throws an exception.
            chart.DataTable.Show = true;
        }