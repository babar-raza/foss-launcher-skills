[Test]
        public void TestShowingAxisTitle()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape = builder.InsertChart(ChartType.Column, 432, 252);

            Chart chart = shape.Chart;
            ChartAxisTitle xTitle = chart.AxisX.Title;
            ChartAxisTitle yTitle = chart.AxisY.Title;

            xTitle.Show = true;
            xTitle.Text = "Categories";
            yTitle.Show = true;
            yTitle.Text = "Values";

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestShowingAxisTitle.docx");
        }