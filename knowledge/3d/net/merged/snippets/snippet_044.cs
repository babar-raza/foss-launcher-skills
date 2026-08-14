[Fact]
        public void OpenStreamWithAutoDetectionGltf_ShouldLoadCorrectly()
        {
            var testFile = "../../../../../../testdata/gltf/simple_cube.gltf";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            using var stream = File.OpenRead(testFile);
            var scene = new Scene();
            var format = FileFormat.Detect(stream, "simple_cube.gltf");
            scene.Open(stream, format.CreateLoadOptions(), CancellationToken.None);

            Assert.NotNull(scene);
            Assert.NotNull(scene.RootNode);
        }