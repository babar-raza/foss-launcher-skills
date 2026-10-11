private static void CheckGridlines(Document doc, string outputFileNameTemplate)
        {
            Shape shape = doc.FirstSection.Body.Shapes[0];
            Chart chart = shape.Chart;
            ChartAxis xAxis = chart.AxisX;
            ChartAxis yAxis = chart.AxisY;

            xAxis.HasMajorGridlines = true;
            xAxis.HasMinorGridlines = true;
            yAxis.HasMajorGridlines = true;
            yAxis.HasMinorGridlines = true;

            TestUtil.SaveCheckGoldExportOnly(doc, string.Format(outputFileNameTemplate, "ShownGridLines"));

            xAxis.HasMajorGridlines = false;
            xAxis.HasMinorGridlines = false;
            yAxis.HasMajorGridlines = false;
            yAxis.HasMinorGridlines = false;

            TestUtil.SaveCheckGoldExportOnly(doc, string.Format(outputFileNameTemplate, "HiddenGridLines"));
        }