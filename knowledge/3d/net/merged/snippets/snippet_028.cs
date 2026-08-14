[Fact]
        public void SaveSceneTo3mfStream_ShouldCreateValidFile()
        {
            var scene = new Scene();
            var box = new Box(2, 2, 2);
            scene.RootNode.CreateChildNode("BoxNode", box);

            using var stream = new MemoryStream();
            var options = new Fmt.Microsoft3MFSaveOptions();
            scene.Save(stream, options);

            stream.Seek(0, SeekOrigin.Begin);
            var content = stream.ToArray();
            
            Assert.True(content.Length > 0);
            
            using var zip = new System.IO.Compression.ZipArchive(new MemoryStream(content), System.IO.Compression.ZipArchiveMode.Read);
            Assert.Equal(3, zip.Entries.Count);
            
            var modelEntry = zip.GetEntry("3D/3dmodel.model");
            Assert.NotNull(modelEntry);
            
            using var reader = new StreamReader(modelEntry.Open());
            var xmlContent = reader.ReadToEnd();
            Assert.Contains("<?xml", xmlContent);
            Assert.Contains("<model", xmlContent);
            Assert.Contains("millimeter", xmlContent);
        }