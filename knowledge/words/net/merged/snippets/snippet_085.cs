[Test]
        public void TestWord2016ChartLegendPosition()
        {
            Document doc = new Document();
            DocumentBuilder builder = new DocumentBuilder(doc);

            Shape shape1 = builder.InsertChart(ChartType.Treemap, 432, 252);

            ChartLegend legend = shape1.Chart.Legend;

            CheckChartExLegendPosition(legend, LegendPosition.Top, SidePosition.Top, PositionAlignment.Center);

            legend.Position = LegendPosition.TopRight;
            CheckChartExLegendPosition(legend, LegendPosition.TopRight, SidePosition.Top, PositionAlignment.Maximum);

            legend.Position = LegendPosition.Bottom;
            CheckChartExLegendPosition(legend, LegendPosition.Bottom, SidePosition.Bottom, PositionAlignment.Center);

            legend.SidePosition = SidePosition.Left;
            CheckChartExLegendPosition(legend, LegendPosition.Left, SidePosition.Left, PositionAlignment.Center);

            legend.PositionAlignment = PositionAlignment.Minimum;
            CheckChartExLegendPosition(legend, LegendPosition.Left, SidePosition.Left, PositionAlignment.Minimum);

            legend.Position = LegendPosition.Left;
            CheckChartExLegendPosition(legend, LegendPosition.Left, SidePosition.Left, PositionAlignment.Minimum);

            legend.Position = LegendPosition.Top;
            CheckChartExLegendPosition(legend, LegendPosition.Top, SidePosition.Top, PositionAlignment.Center);

            legend.PositionAlignment = PositionAlignment.Maximum;
            CheckChartExLegendPosition(legend, LegendPosition.TopRight, SidePosition.Top, PositionAlignment.Maximum);
        }