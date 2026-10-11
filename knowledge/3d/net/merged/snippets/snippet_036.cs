[Fact]
        public void LoadSceneFromPlyWithLoadOptions_ShouldLoadCorrectly()
        {
            var testFile = "../../../../../../testdata/input/cube.ply";

            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            using var stream = File.OpenRead(testFile);
            var scene = new Scene();
            var options = new Fmt.PlyLoadOptions();
            scene.Open(stream, options, CancellationToken.None);

            Assert.NotNull(scene);
            Assert.NotNull(scene.RootNode);
            Assert.True(scene.RootNode.ChildNodes.Count > 0);

            var node = scene.RootNode.ChildNodes[0];
            var meshEntity = node.Entities[0] as Mesh;
            Assert.NotNull(meshEntity);
            Assert.Equal(8, meshEntity.ControlPoints.Count);
            Assert.Equal(6, meshEntity.PolygonCount);
        }