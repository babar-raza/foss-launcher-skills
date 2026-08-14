[Fact]
         public void DetectStlFormatFromStreamWithFilename_ShouldReturnStlFormat()
         {
             var testFile = Path.Combine("../../../../../../testdata/stl", "stl_ascii.stl");

             if (!File.Exists(testFile))
             {
                 throw new FileNotFoundException($"Test file not found: {testFile}");
             }
using var stream = File.OpenRead(testFile);
             var format = FileFormat.Detect(stream, "test.");            Assert.Equal(".stl", format.Extension);
        }