[Fact]
          public void LoadSceneFromFbxWithLoadOptions_ShouldLoadCorrectly()
        {
            var testFile = "../../../../../../testdata/input/cube.fbx";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            using var stream = File.OpenRead(testFile);
            var scene = new Scene();
            var options = new Fmt.FbxLoadOptions();
            scene.Open(stream, options, CancellationToken.None);

            Assert.NotNull(scene);
             Assert.NotNull(scene.RootNode);
             Assert.True(scene.RootNode.ChildNodes.Count > 0);

              var node = scene.RootNode.ChildNodes[0];
              Assert.NotNull(node.Entities);
          }