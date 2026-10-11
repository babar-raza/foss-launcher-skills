[Fact]
        public void Save3DSFile_ShouldExportScene()
        {
            var testDataPath = GetTestDataPath();
            var testFile = Path.Combine(testDataPath, "3ds", "test.3DS");

            // Load a 3DS file
            var scene = new Scene();
            scene.Open(testFile);

            // Save to a temporary file
            var tempFile = Path.Combine(Path.GetTempPath(), $"export-test-{Guid.NewGuid()}.3ds");
            try
            {
                scene.Save(tempFile, new Discreet3dsSaveOptions());

                // Verify the file was created
                Assert.True(File.Exists(tempFile), "Exported file should exist");

                // Verify we can re-open the file
                var reOpenedScene = new Scene();
                reOpenedScene.Open(tempFile);

                Assert.NotNull(reOpenedScene);
                Assert.NotNull(reOpenedScene.RootNode);
            }
            finally
            {
                if (File.Exists(tempFile))
                {
                    File.Delete(tempFile);
                }
            }
        }