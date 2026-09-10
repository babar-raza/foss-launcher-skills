private static bool IsMasterPart(string partName) =>
        (partName.StartsWith("ppt/slideMasters/", StringComparison.Ordinal)
            || partName.StartsWith("ppt/notesMasters/", StringComparison.Ordinal)
            || partName.StartsWith("ppt/handoutMasters/", StringComparison.Ordinal))
        && partName.EndsWith(".xml", StringComparison.Ordinal);