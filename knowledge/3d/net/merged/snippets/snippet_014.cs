[Fact]
        public void LoadSceneFromStlAscii_ShouldLoadCorrectly()
        {
            var testFile = Path.Combine("../../../../../../testdata/stl", "stl_ascii.stl");

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
            Assert.True(node.Entities.Count > 0);

             var mesh = node.Entities[0] as Mesh;
             Assert.NotNull(mesh);
             Assert.True(mesh.ControlPoints.Count > 0);
             Assert.True(mesh.PolygonCount > 0);
         }