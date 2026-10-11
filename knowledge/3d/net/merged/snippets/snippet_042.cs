[Fact]
        public void OpenStreamWithAutoDetectionObj_ShouldLoadCorrectly()
        {
            var testFile = "../../../../../../testdata/input/cube.obj";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            using var stream = File.OpenRead(testFile);
            var scene = new Scene();
            var format = FileFormat.GetFormatByExtension(Path.GetExtension(Path.GetFileName(testFile)));
            scene.Open(stream, format, CancellationToken.None);

            Assert.NotNull(scene);
            Assert.NotNull(scene.RootNode);
            Assert.True(scene.RootNode.ChildNodes.Count > 0);

            var node = scene.RootNode.ChildNodes[0];
            Assert.NotNull(node.Entities);
            Assert.True(node.Entities.Count > 0);

            var mesh = node.Entities[0] as Mesh;
            Assert.NotNull(mesh);
            Assert.Equal(8, mesh.ControlPoints.Count);
            Assert.Equal(3, mesh.PolygonCount);
        }