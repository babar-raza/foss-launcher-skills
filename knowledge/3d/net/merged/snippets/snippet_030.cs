[Fact]
        public void SaveSceneTo3mfWithPrimitive_ShouldCreateValidFile()
        {
            var scene = new Scene();
            var sphere = new Sphere(1);
            scene.RootNode.CreateChildNode("SphereNode", sphere);

            using var stream = new MemoryStream();
            var options = new Fmt.Microsoft3MFSaveOptions();
            scene.Save(stream, options);

            stream.Seek(0, SeekOrigin.Begin);
            
            using var zip = new System.IO.Compression.ZipArchive(new MemoryStream(stream.ToArray()), System.IO.Compression.ZipArchiveMode.Read);
            var modelEntry = zip.GetEntry("3D/3dmodel.model");
            Assert.NotNull(modelEntry);
            
            using var reader = new StreamReader(modelEntry.Open());
            var xmlContent = reader.ReadToEnd();
            Assert.Contains("<mesh", xmlContent);
            Assert.Contains("<vertices", xmlContent);
            Assert.Contains("<triangles", xmlContent);
        }