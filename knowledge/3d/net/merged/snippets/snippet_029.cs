[Fact]
        public void SaveSceneTo3mfFile_ShouldCreateValidFile()
        {
            var scene = new Scene();
            var box = new Box(2, 2, 2);
            scene.RootNode.CreateChildNode("BoxNode", box);

            var outputFile = Path.Combine(Path.GetTempPath(), "test_output.3mf");
            try
            {
                scene.Save(outputFile);
                
                Assert.True(File.Exists(outputFile));
                
                using var zip = new System.IO.Compression.ZipArchive(File.OpenRead(outputFile), System.IO.Compression.ZipArchiveMode.Read);
                Assert.Equal(3, zip.Entries.Count);
                
                var modelEntry = zip.GetEntry("3D/3dmodel.model");
                Assert.NotNull(modelEntry);
            }
            finally
            {
                if (File.Exists(outputFile))
                {
                    File.Delete(outputFile);
                }
            }
        }