[Test]
        public void TestDataLabelOrientationInNewChart()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape1 = builder.InsertChart(ChartType.Column, 432, 252);
            ChartSeries series1 = shape1.Chart.Series[0];
            ChartDataLabelCollection dataLabels1 = series1.DataLabels;

            series1.HasDataLabels = true;
            dataLabels1.ShowValue = true;
            dataLabels1.ShowCategoryName = true;
            dataLabels1.Format.ShapeType = ChartShapeType.UpArrow;
            dataLabels1.Format.Stroke.Fill.Solid(Color.DarkBlue);

            dataLabels1.Orientation = ShapeTextOrientation.VerticalFarEast;
            dataLabels1.Rotation = -10;

            dataLabels1[1].Orientation = ShapeTextOrientation.Horizontal;
            dataLabels1[1].Rotation = 45;

            dataLabels1[2].Orientation = ShapeTextOrientation.WordArtVertical;

            dataLabels1[3].Rotation = 5;

            Assert.That(dataLabels1.Orientation, Is.EqualTo(ShapeTextOrientation.VerticalFarEast));
            Assert.That(dataLabels1.Rotation, Is.EqualTo(-10));
            CheckOrientation(dataLabels1[0], ShapeTextOrientation.VerticalFarEast, -10);
            CheckOrientation(dataLabels1[1], ShapeTextOrientation.Horizontal, 45);
            CheckOrientation(dataLabels1[2], ShapeTextOrientation.WordArtVertical, -10);
            CheckOrientation(dataLabels1[3], ShapeTextOrientation.VerticalFarEast, 5);

            // Test setting properties of individual data labels without setting properties of the collection.

            Shape shape2 = builder.InsertChart(ChartType.Column, 432, 252);
            ChartSeries series2 = shape2.Chart.Series[0];
            ChartDataLabelCollection dataLabels2 = series2.DataLabels;

            series2.HasDataLabels = true;
            dataLabels2.ShowValue = true;
            dataLabels2.ShowCategoryName = true;
            dataLabels2.Format.ShapeType = ChartShapeType.UpArrow;
            dataLabels2.Format.Stroke.Fill.Solid(Color.DarkBlue);

            Assert.That(dataLabels2.Orientation, Is.EqualTo(ShapeTextOrientation.Horizontal));
            Assert.That(dataLabels2.Rotation, Is.EqualTo(0));

            dataLabels2[1].Orientation = ShapeTextOrientation.Downward;
            dataLabels2[1].Rotation = 10;

            dataLabels2[2].Orientation = ShapeTextOrientation.Upward;

            dataLabels2[3].Rotation = 15;

            Assert.That(dataLabels2.Orientation, Is.EqualTo(ShapeTextOrientation.Horizontal));
            Assert.That(dataLabels2.Rotation, Is.EqualTo(0));
            CheckOrientation(dataLabels2[0], ShapeTextOrientation.Horizontal, 0);
            CheckOrientation(dataLabels2[1], ShapeTextOrientation.Downward, 10);
            CheckOrientation(dataLabels2[2], ShapeTextOrientation.Upward, 0);
            CheckOrientation(dataLabels2[3], ShapeTextOrientation.Horizontal, 15);

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestLabelOrientationInNewChart.docx", null, true);

            shape1 = doc.FirstSection.Body.Shapes[0];
            series1 = shape1.Chart.Series[0];
            dataLabels1 = series1.DataLabels;

            Assert.That(dataLabels1.Orientation, Is.EqualTo(ShapeTextOrientation.VerticalFarEast));
            Assert.That(dataLabels1.Rotation, Is.EqualTo(-10));
            CheckOrientation(dataLabels1[0], ShapeTextOrientation.VerticalFarEast, -10);
            CheckOrientation(dataLabels1[1], ShapeTextOrientation.Horizontal, 45);
            CheckOrientation(dataLabels1[2], ShapeTextOrientation.WordArtVertical, -10);
            CheckOrientation(dataLabels1[3], ShapeTextOrientation.VerticalFarEast, 5);

            shape2 = doc.FirstSection.Body.Shapes[1];
            series2 = shape2.Chart.Series[0];
            dataLabels2 = series2.DataLabels;

            Assert.That(dataLabels2.Orientation, Is.EqualTo(ShapeTextOrientation.Horizontal));
            Assert.That(dataLabels2.Rotation, Is.EqualTo(0));
            CheckOrientation(dataLabels2[0], ShapeTextOrientation.Horizontal, 0);
            CheckOrientation(dataLabels2[1], ShapeTextOrientation.Downward, 10);
            CheckOrientation(dataLabels2[2], ShapeTextOrientation.Upward, 0);
            CheckOrientation(dataLabels2[3], ShapeTextOrientation.Horizontal, 15);
        }