[Test]
        public void TestGridLines()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);
            builder.InsertChart(ChartType.Bar, 432, 252);
            CheckGridlines(doc, @"Model\Charts\Test{0}.docx");
        }