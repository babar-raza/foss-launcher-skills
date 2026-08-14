[Fact]
        public void DetectObjFormatFromStreamWithFilename_ShouldReturnObjFormat()
        {
            var testFile = "../../../../../../testdata/input/cube.obj";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }using var stream = File.OpenRead(testFile);
             var format = FileFormat.Detect(stream, "test.obj");
             Assert.Equal(".obj", format.Extension);
         }