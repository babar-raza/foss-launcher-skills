[Fact]
        public void DetectObjFormatFromStream_ShouldReturnObjFormat()
        {
            var testFile = "../../../../../../testdata/input/cube.obj";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }
using var stream = File.OpenRead(testFile);
             var format = FileFormat.Detect(stream, null);
            Assert.Equal(".obj", format.Extension);
        }