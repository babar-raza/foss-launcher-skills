[Fact]
        public void SaveSceneToObjFrom3mf_ShouldIncludePolygons()
        {
            var testFile = "../../../../../../testdata/3mf/box.3mf";
            
            if (!File.Exists(testFile))
            {
                throw new FileNotFoundException($"Test file not found: {testFile}");
            }

            var scene = new Scene();
            scene.Open(testFile);

            using var stream = new MemoryStream();
            var options = new Fmt.ObjSaveOptions() { Verbose = true };
            scene.Save(stream, options);

            stream.Seek(0, SeekOrigin.Begin);
            var content = new StreamReader(stream).ReadToEnd();

            Assert.Contains("v ", content);
            Assert.Contains("f ", content);
            
            var lines = content.Split('\n', StringSplitOptions.RemoveEmptyEntries);
            var faceLines = lines.Where(l => l.StartsWith("f ")).ToArray();
            Assert.True(faceLines.Length > 0, "Should have at least some face definitions");
        }