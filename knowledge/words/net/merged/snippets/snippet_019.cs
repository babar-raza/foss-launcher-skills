[Test]
        public void TestTickLabelsOrientationInNewChart()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape1 = builder.InsertChart(ChartType.Column, 432, 252);
            AxisTickLabels axisX1TickLabels = shape1.Chart.AxisX.TickLabels;
            AxisTickLabels axisY1TickLabels = shape1.Chart.AxisY.TickLabels;

            axisX1TickLabels.Orientation = ShapeTextOrientation.VerticalFarEast;
            axisX1TickLabels.Rotation = -10;
            axisY1TickLabels.Orientation = ShapeTextOrientation.Horizontal;
            axisY1TickLabels.Rotation = 45;

            Shape shape2 = builder.InsertChart(ChartType.Column, 432, 252);
            AxisTickLabels axisX2TickLabels = shape2.Chart.AxisX.TickLabels;
            AxisTickLabels axisY2TickLabels = shape2.Chart.AxisY.TickLabels;

            axisX2TickLabels.Orientation = ShapeTextOrientation.WordArtVertical;
            axisY2TickLabels.Rotation = 5;

            CheckOrientation(axisX1TickLabels, ShapeTextOrientation.VerticalFarEast, -10);
            CheckOrientation(axisY1TickLabels, ShapeTextOrientation.Horizontal, 45);
            CheckOrientation(axisX2TickLabels, ShapeTextOrientation.WordArtVertical, 0);
            CheckOrientation(axisY2TickLabels, ShapeTextOrientation.Horizontal, 5);

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestTickLabelsOrientationInNewChart.docx", null, true);

            shape1 = doc.FirstSection.Body.Shapes[0];
            axisX1TickLabels = shape1.Chart.AxisX.TickLabels;
            axisY1TickLabels = shape1.Chart.AxisY.TickLabels;
            shape2 = doc.FirstSection.Body.Shapes[1];
            axisX2TickLabels = shape2.Chart.AxisX.TickLabels;
            axisY2TickLabels = shape2.Chart.AxisY.TickLabels;

            CheckOrientation(axisX1TickLabels, ShapeTextOrientation.VerticalFarEast, -10);
            CheckOrientation(axisY1TickLabels, ShapeTextOrientation.Horizontal, 45);
            CheckOrientation(axisX2TickLabels, ShapeTextOrientation.WordArtVertical, 0);
            CheckOrientation(axisY2TickLabels, ShapeTextOrientation.Horizontal, 5);
        }