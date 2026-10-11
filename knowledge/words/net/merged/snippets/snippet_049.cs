private static bool FillSupportedPositions(ChartSeriesType seriesType, List<ChartDataLabelPosition> list)
        {
            list.Clear();

            foreach (ChartDataLabelPosition position in Enum.GetValues(typeof(ChartDataLabelPosition)))
            {
                if (DmlChartUtil.IsDataLabelPositionSupported(seriesType, position))
                    list.Add(position);
            }

            return (list.Count > 0);
        }