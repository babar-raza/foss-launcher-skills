private static string GetTestDataPath()
        {
            var assemblyDir = Path.GetDirectoryName(typeof(Test3DSImport).Assembly.Location);
            // Go up 8 levels from bin/Debug/net10.0/ to get to workspace root
            // then use the TestData folder (symlinked from foss.3d.net)
            var testDataPath = Path.Combine(assemblyDir, "..", "..", "..", "..", "..", "..", "..", "..", "TestData");
            return Path.GetFullPath(testDataPath);
        }