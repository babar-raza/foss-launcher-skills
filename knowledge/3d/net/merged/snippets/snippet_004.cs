[Fact]
        public void SaveSceneToCollada_ShouldCreateValidFile()
        {
            var scene = new Scene();
            var box = new Box(2, 2, 2);
            var node = scene.RootNode.CreateChildNode("BoxNode", box);
            
            var outputFile = Path.Combine(Path.GetTempPath(), "test_output.dae");
            try
            {
                scene.Save(outputFile);

                Assert.True(File.Exists(outputFile));
                var content = File.ReadAllText(outputFile);
                Assert.Contains("COLLADA", content);
                Assert.Contains("<geometry", content);
                Assert.Contains("<node", content);
            }
            finally
            {
                if (File.Exists(outputFile))
                {
                    File.Delete(outputFile);
                }
            }
        }