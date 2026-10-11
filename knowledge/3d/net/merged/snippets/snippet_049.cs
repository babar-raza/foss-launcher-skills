private static string GetTestDataPath()
        {
            var assemblyDir = Path.GetDirectoryName(typeof(Test3DSExport).Assembly.Location);
            var testDataPath = Path.Combine(assemblyDir, "..", "..", "..", "..", "..", "..", "..", "..", "TestData");
            return Path.GetFullPath(testDataPath);
        }