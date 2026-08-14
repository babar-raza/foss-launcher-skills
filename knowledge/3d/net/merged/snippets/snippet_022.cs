[Fact]
        public void LoadSceneFromStreamGltf_ShouldLoadCorrectly()
        {
            var testFile = "../../../../../../testdata/gltf/simple_cube.gltf";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            using var stream = File.OpenRead(testFile);
            var scene = new Scene();
            var options = new Fmt.GltfLoadOptions();
            scene.Open(stream, options, CancellationToken.None);

            Assert.NotNull(scene);
            Assert.NotNull(scene.RootNode);
        }