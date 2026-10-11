private static void AssertSamePartSet(string inputPath, string producedPath)
    {
        using var input = PptxPackage.Open(inputPath);
        using var produced = PptxPackage.Open(producedPath);

        var before = input.PartNames.ToHashSet(StringComparer.Ordinal);
        var after = produced.PartNames.ToHashSet(StringComparer.Ordinal);

        var lost = before.Except(after).Order(StringComparer.Ordinal).ToList();
        var added = after.Except(before).Order(StringComparer.Ordinal).ToList();

        Assert.True(lost.Count == 0 && added.Count == 0,
            $"The saved package does not hold the parts it was opened with " +
            $"({before.Count} in, {after.Count} out)." +
            $"{Environment.NewLine}lost:  {(lost.Count == 0 ? "none" : string.Join(", ", lost))}" +
            $"{Environment.NewLine}added: {(added.Count == 0 ? "none" : string.Join(", ", added))}");
    }