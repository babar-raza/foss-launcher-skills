[Fact]
        public void LoadSceneFromFbx_ShouldLoadCorrectly()
        {
            var testFile = "../../../../../../testdata/input/cube.fbx";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            var scene = new Scene();
            scene.Open(testFile);

            Assert.NotNull(scene);
             Assert.NotNull(scene.RootNode);
             Assert.True(scene.RootNode.ChildNodes.Count > 0);

              var node = scene.RootNode.ChildNodes[0];
              Assert.NotNull(node.Entities);
          }