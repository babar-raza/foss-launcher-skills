[Test]
        public void TestLeftTopWithAbsoluteCoordinates()
        {
            SystemPal.SaveCulture();
            try
            {
                SystemPal.SetStandardCulture();

                Document doc = new Document();
                DocumentBuilder builder = new DocumentBuilder(doc);

                // Test moving labels of a doughnut chart so that they are outside of the chart ring as some
                // customers requested.
                // Let's generate a lots of values, and place the labels around a large circle.

                // All constants are in points.
                const int width = 432;
                const int height = 252;
                const int ringR = 88;
                const int ringCenterY = 139;
                const int titleArea = 22;
                const int marginY = 3;

                Shape shape = builder.InsertChart(ChartType.Doughnut, width, height);
                Chart chart = shape.Chart;
                chart.Title.Text = "Test moving labels";
                chart.Legend.Position = LegendPosition.None;

                ChartSeries series = chart.Series[0];
                series.ClearValues();
                double total = 0;
                for (double n = 5; n >= 1; n -= 0.2)
                {
                    series.Add(ChartXValue.FromString(string.Format("XYZ{0:F1}", n)), ChartYValue.FromDouble(n));
                    total += n;
                }

                series.HasDataLabels = true;
                ChartDataLabelCollection dataLabels = series.DataLabels;
                dataLabels.ShowCategoryName = true;
                dataLabels.ShowValue = false;
                dataLabels.ShowLeaderLines = true;

                double labelHeight = dataLabels.Font.Size * 1.65;
                double labelWidth = dataLabels.Font.Size * series.XValues[0].StringValue.Length * 0.5875;
                double newLabelRingR = ringR + labelWidth;
                // These coordinates are calculated with a center located at the chart ring center and the Y-axis
                // pointing upward.
                double maxY = ringCenterY - (titleArea + marginY + labelHeight / 2);
                double minY = ringCenterY - (height - marginY - labelHeight / 2);
                double totalAngle = 0;
                double previousX = 0;
                double previousY = 0;

                for (int i = 0; i < series.ValueCount; i++)
                {
                    ChartDataLabel dataLabel = dataLabels[i];
                    if ((i > 0) && dataLabels[i - 1].IsHidden)
                    {
                        dataLabel.IsHidden = true;
                        continue;
                    }

                    double angle = series.YValues[i].DoubleValue / total * 2 * System.Math.PI;
                    double labelAngle = angle / 2 + totalAngle;

                    // These coordinates are calculated with a center located at the chart ring center and the Y-axis
                    // pointing upward.
                    double newLocationX = newLabelRingR * System.Math.Sin(labelAngle);
                    double newLocationY = newLabelRingR * System.Math.Cos(labelAngle);
                    if (newLocationY > maxY)
                        newLocationY = maxY;
                    if (newLocationY < minY)
                        newLocationY = minY;
                    if ((i > 0) && (System.Math.Abs(newLocationY - previousY) < labelHeight))
                    {
                        if (MathUtil.AreEqual(newLocationY, minY))
                        {
                            if (newLocationX > previousX - labelWidth)
                                newLocationX = previousX - labelWidth;
                        }
                        else
                        {
                            newLocationY = previousY + ((labelAngle < System.Math.PI)
                                ? -labelHeight
                                : labelHeight);
                            if (newLocationY > maxY)
                            {
                                // Hide this and further data labels.
                                dataLabel.IsHidden = true;
                                continue;
                            }
                        }
                    }

                    dataLabel.Left = newLocationX + width / 2d - labelWidth / 2;
                    dataLabel.LeftMode = ChartDataLabelLocationMode.Absolute;
                    dataLabel.Top = ringCenterY - newLocationY - labelHeight / 2;
                    dataLabel.TopMode = ChartDataLabelLocationMode.Absolute;

                    totalAngle += angle;
                    previousX = newLocationX;
                    previousY = newLocationY;
                }

                TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestDataLabelLeftT