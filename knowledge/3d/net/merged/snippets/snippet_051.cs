[Fact]
        public void Save3DSFile_ShouldSaveMesh()
        {
            var testDataPath = GetTestDataPath();
            var testFile = Path.Combine(testDataPath, "3ds", "cube.3DS");

            var originalScene = new Scene();
            originalScene.Open(testFile);

            var tempFile = Path.Combine(Path.GetTempPath(), $"export-mesh-{Guid.NewGuid()}.3ds");
            try
            {
                originalScene.Save(tempFile, FileFormat.Discreet3DS);

                var reOpenedScene = new Scene();
                reOpenedScene.Open(tempFile);

                int originalMeshCount = 0;
                int reOpenedMeshCount = 0;
                int originalVertices = 0;
                int reOpenedVertices = 0;
                int originalFaces = 0;
                int reOpenedFaces = 0;

                CountMeshes(originalScene.RootNode, ref originalMeshCount, ref originalVertices, ref originalFaces);
                CountMeshes(reOpenedScene.RootNode, ref reOpenedMeshCount, ref reOpenedVertices, ref reOpenedFaces);

                Assert.Equal(originalMeshCount, reOpenedMeshCount);
                Assert.True(reOpenedVertices > 0);
                Assert.True(reOpenedFaces > 0);
            }
            finally
            {
                if (File.Exists(tempFile))
                {
                    File.Delete(tempFile);
                }
            }
        }