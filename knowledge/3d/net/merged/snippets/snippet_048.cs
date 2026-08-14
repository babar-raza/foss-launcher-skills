[Fact]
        public void DetectGltfFormatFromStreamWithFilename_ShouldReturnGltfFormat()
        {
            var testFile = "../../../../../../testdata/gltf/simple_cube.gltf";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            using var stream = File.OpenRead(testFile);
            var format = FileFormat.Detect(stream, "test.gltf");

            Assert.Equal(".gltf", format.Extension);
        }