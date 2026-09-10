private static void AssertEachMasterHasItsOwnTheme(PptxPackage package)
    {
        var masters = package.ContentPartNames
            .Where(IsMasterPart)
            .ToList();

        Assert.True(masters.Count > 0,
            $"The package has no master parts at all. Parts: {string.Join(", ", package.PartNames)}");

        var themeOfMaster = new Dictionary<string, string>(StringComparer.Ordinal);

        foreach (var master in masters)
        {
            var themes = package.Relationships(master)
                .Where(relationship => relationship.Type == Ns.ThemeRelationshipType)
                .Select(relationship => PptxPackage.ResolveTarget(master, relationship.Target))
                .ToList();

            Assert.True(themes.Count == 1,
                $"{master} relates to {themes.Count} theme part(s), expected exactly one." +
                $"{Environment.NewLine}{PackageAssert.Describe(package, PptxPackage.RelationshipsPartNameFor(master))}");

            themeOfMaster[master] = themes[0];
        }

        var shared = themeOfMaster
            .GroupBy(pair => pair.Value, StringComparer.OrdinalIgnoreCase)
            .Where(group => group.Count() > 1)
            .Select(group => $"'{group.Key}' is related from {string.Join(" and ", group.Select(pair => pair.Key))}")
            .ToList();

        Assert.True(shared.Count == 0,
            $"{shared.Count} theme part(s) are shared between masters:{Environment.NewLine}" +
            string.Join(Environment.NewLine, shared));
    }