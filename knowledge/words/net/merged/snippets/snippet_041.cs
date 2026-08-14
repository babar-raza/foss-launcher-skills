[Test]
        public void TestDataLabelOrientationInExistingChart()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestDataLabelOrientation.docx");
            Shape shape = doc.FirstSection.Body.Shapes[0];
            ChartSeries series = shape.Chart.Series[0];
            ChartDataLabelCollection dataLabels = series.DataLabels;

            Assert.That(dataLabels.Orientation, Is.EqualTo(ShapeTextOrientation.Horizontal));
            Assert.That(dataLabels.Rotation, Is.EqualTo(0));
            CheckOrientation(dataLabels[0], ShapeTextOrientation.Horizontal, 15);
            CheckOrientation(dataLabels[1], ShapeTextOrientation.VerticalFarEast, 15);
            CheckOrientation(dataLabels[2], ShapeTextOrientation.VerticalRotatedFarEast, 15);
            CheckOrientation(dataLabels[3], ShapeTextOrientation.Downward, 15);
            CheckOrientation(dataLabels[4], ShapeTextOrientation.Upward, 15);
            CheckOrientation(dataLabels[5], ShapeTextOrientation.WordArtVertical, 15);
            CheckOrientation(dataLabels[6], ShapeTextOrientation.WordArtVerticalRightToLeft, 15);

            dataLabels[0].Orientation = ShapeTextOrientation.WordArtVerticalRightToLeft;
            dataLabels[0].Rotation = 0;

            dataLabels[1].Orientation = ShapeTextOrientation.Horizontal;

            dataLabels[2].Rotation = -15;

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestDataLabelOrientation.docx", null, true);

            shape = doc.FirstSection.Body.Shapes[0];
            series = shape.Chart.Series[0];
            dataLabels = series.DataLabels;

            CheckOrientation(dataLabels[0], ShapeTextOrientation.WordArtVerticalRightToLeft, 0);
            CheckOrientation(dataLabels[1], ShapeTextOrientation.Horizontal, 15);
            CheckOrientation(dataLabels[2], ShapeTextOrientation.VerticalRotatedFarEast, -15);
        }