private static Document CreateDocumentWithChart()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Line, 432, 252);
            Chart chart = shape.Chart;

            // Delete default generated series.
            chart.Series.Clear();

            string[] categories = new string[] { "AW Category 1", "AW Category 2", "AW Category 3" };
            chart.Series.Add("AW Series 1", categories, new double[] { 4.3, 2.5, 3.5 });

            return doc;
        }