[Test]
        public void TestNewChartAxisTitle()
        {
            // Axis title text depends on current culture.
            SystemPal.SaveCulture();
            SystemPal.SetStandardCulture();
            try
            {
                Document doc = new Document();
                DocumentBuilder builder = new DocumentBuilder(doc);

                Shape shape = builder.InsertChart(ChartType.Bar, 432, 252);
                Chart chart = shape.Chart;

                ChartAxisTitle xTitle = chart.AxisX.Title;
                CheckTitle(xTitle, false, false, "Axis Title");
                ChartAxisTitle yTitle = chart.AxisY.Title;
                CheckTitle(yTitle, false, false, "Axis Title");

                xTitle.Text = "Category";
                xTitle.Overlay = true;
                xTitle.Show = true;

                yTitle.Show = true;
                yTitle.Overlay = true;
                yTitle.Text = "Value";

                CheckTitle(xTitle, true, true, "Category");
                CheckTitle(yTitle, true, true, "Value");

                doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestNewChartAxisTitle.docx", null, false);
                shape = doc.FirstSection.Body.Shapes[0];
                chart = shape.Chart;

                CheckTitle(chart.AxisX.Title, true, true, "Category");
                CheckTitle(chart.AxisY.Title, true, true, "Value");
            }
            finally
            {
                SystemPal.RestoreCulture();
            }
        }