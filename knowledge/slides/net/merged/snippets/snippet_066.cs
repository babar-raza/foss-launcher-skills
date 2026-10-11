[Fact]
    public void EachRequestedFormatProducesADifferentPackage()
    {
        var written = new Dictionary<string, string>(StringComparer.Ordinal);

        foreach (var format in Enum.GetValues<SaveFormat>())
        {
            var path = _workspace.PathFor($"distinct-{format}.{format.ToString().ToLowerInvariant()}");
            using var presentation = new Presentation();
            try
            {
                presentation.Save(path, format);
            }
            catch (NotSupportedException)
            {
                continue;
            }

            written[format.ToString()] = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));
        }

        var distinct = written.Values.Distinct(StringComparer.Ordinal).Count();

        Assert.True(distinct == written.Count,
            $"{written.Count} formats were written and only {distinct} distinct file(s) came out — " +
            $"the format argument made no difference to the bytes.{Environment.NewLine}" +
            string.Join(Environment.NewLine, written.Select(pair => $"  {pair.Key,-6} {pair.Value[..16]}")));
    }