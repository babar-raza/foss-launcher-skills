[Fact]
        public void Save3DSFile_ShouldSaveMaterials()
        {
            var testDataPath = GetTestDataPath();
            var testFile = Path.Combine(testDataPath, "3ds", "test.3DS");

            var originalScene = new Scene();
            originalScene.Open(testFile);

            var tempFile = Path.Combine(Path.GetTempPath(), $"export-materials-{Guid.NewGuid()}.3ds");
            try
            {
                originalScene.Save(tempFile, FileFormat.Discreet3DS);

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