private static ChartXValue GetNewXValue(ChartSeries series)
        {
            int valueCount = series.ValueCount;
            Debug.Assert(valueCount > 1);

            switch (series.XValues[0].ValueType)
            {
                case ChartXValueType.String:
                    return ChartXValue.FromString("Category " + valueCount);
                case ChartXValueType.Double:
                    double lastX = series.XValues[valueCount - 1].DoubleValue;
                    return ChartXValue.FromDouble(lastX + (lastX - series.XValues[valueCount - 2].DoubleValue));
                case ChartXValueType.Multilevel:
                    ChartMultilevelValue lastValue = series.XValues[valueCount - 1].MultilevelValue;
                    return ChartXValue.FromMultilevelValue(
                        new ChartMultilevelValue(lastValue.Level1, lastValue.Level2, "Leaf " + valueCount));
                case ChartXValueType.DateTime:
                case ChartXValueType.Time:
                default:
                    throw new InvalidOperationException("Unexpected X value type.");
            }
        }