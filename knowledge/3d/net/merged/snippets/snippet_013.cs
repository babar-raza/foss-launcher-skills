[Fact]
        public void SaveSceneToStl_ShouldCreateValidFile()
        {
            var scene = new Scene();
            var box = new Box(2, 2, 2);
            var node = scene.RootNode.CreateChildNode("BoxNode", box);

            var outputFile = Path.Combine(Path.GetTempPath(), "test_output.stl");
            try
            {
                scene.Save(outputFile);

                Assert.True(File.Exists(outputFile));
                var content = File.ReadAllBytes(outputFile);
                Assert.True(content.Length > 84);
            }
            finally
            {
                if (File.Exists(outputFile))
                {
                    File.Delete(outputFile);
                }
            }
        }