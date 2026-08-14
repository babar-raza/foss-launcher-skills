private static ITable? FindTable(ISlide slide)
    {
        foreach (var shape in slide.Shapes!)
        {
            if (shape is Table table)
                return table;
        }
        return null;
    }