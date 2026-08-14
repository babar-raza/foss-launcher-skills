[Fact]
        public void Save3DSFile_ShouldSaveScene()
        {
            var testDataPath = GetTestDataPath();
            var testFile = Path.Combine(testDataPath, "3ds", "test.3DS");

            var scene = new Scene();
            scene.Open(testFile);

            var tempFile = Path.Combine(Path.GetTempPath(), $"export-roundtrip-{Guid.NewGuid()}.3ds");
            try
            {
                scene.Save(tempFile, FileFormat.Discreet3DS);

                Assert.True(File.Exists(tempFile), "Exported file should exist");

                var reOpenedScene = new Scene();
                reOpenedScene.Open(tempFile);

                Assert.NotNull(reOpenedScene);
                Assert.NotNull(reOpenedScene.RootNode);
                Assert.NotNull(reOpenedScene.RootNode.ChildNodes);
            }
            finally
            {
                if (File.Exists(tempFile))
                {
                    File.Delete(tempFile);
                }
            }
        }