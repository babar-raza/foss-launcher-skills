[Test]
        public void TestTickLabelsOrientationInExistingChart()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestTickLabelsOrientation.docx");
            Shape shape1 = doc.FirstSection.Body.Shapes[0];
            AxisTickLabels axisX1TickLabels = shape1.Chart.AxisX.TickLabels;
            AxisTickLabels axisY1TickLabels = shape1.Chart.AxisY.TickLabels;
            Shape shape2 = doc.FirstSection.Body.Shapes[1];
            AxisTickLabels axisX2TickLabels = shape2.Chart.AxisX.TickLabels;
            AxisTickLabels axisY2TickLabels = shape2.Chart.AxisY.TickLabels;

            CheckOrientation(axisX1TickLabels, ShapeTextOrientation.Horizontal, 85);
            CheckOrientation(axisY1TickLabels, ShapeTextOrientation.Horizontal, -90);
            CheckOrientation(axisX2TickLabels, ShapeTextOrientation.WordArtVertical, 20);
            CheckOrientation(axisY2TickLabels, ShapeTextOrientation.Horizontal, 0);

            axisX1TickLabels.Orientation = ShapeTextOrientation.WordArtVerticalRightToLeft;
            axisX1TickLabels.Rotation = 0;

            axisY1TickLabels.Rotation = -10;

            axisX2TickLabels.Orientation = ShapeTextOrientation.VerticalFarEast;

            axisY2TickLabels.Rotation = 10;

            CheckOrientation(axisX1TickLabels, ShapeTextOrientation.WordArtVerticalRightToLeft, 0);
            CheckOrientation(axisY1TickLabels, ShapeTextOrientation.Horizontal, -10);
            CheckOrientation(axisX2TickLabels, ShapeTextOrientation.VerticalFarEast, 20);
            CheckOrientation(axisY2TickLabels, ShapeTextOrientation.Horizontal, 10);

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestTickLabelsOrientation.docx", null, true);

            shape1 = doc.FirstSection.Body.Shapes[0];
            axisX1TickLabels = shape1.Chart.AxisX.TickLabels;
            axisY1TickLabels = shape1.Chart.AxisY.TickLabels;
            shape2 = doc.FirstSection.Body.Shapes[1];
            axisX2TickLabels = shape2.Chart.AxisX.TickLabels;
            axisY2TickLabels = shape2.Chart.AxisY.TickLabels;

            CheckOrientation(axisX1TickLabels, ShapeTextOrientation.WordArtVerticalRightToLeft, 0);
            CheckOrientation(axisY1TickLabels, ShapeTextOrientation.Horizontal, -10);
            CheckOrientation(axisX2TickLabels, ShapeTextOrientation.VerticalFarEast, 20);
            CheckOrientation(axisY2TickLabels, ShapeTextOrientation.Horizontal, 10);
        }