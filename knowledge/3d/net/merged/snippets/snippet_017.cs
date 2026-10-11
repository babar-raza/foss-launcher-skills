[Fact]
        public void SaveSceneToStreamObj_ShouldCreateValidOutput()
        {
            var scene = new Scene();
            var box = new Box(2, 2, 2);
            scene.RootNode.CreateChildNode("BoxNode", box);

            using var stream = new MemoryStream();
            var options = new Fmt.ObjSaveOptions();
            scene.Save(stream, options);

            stream.Seek(0, SeekOrigin.Begin);
            var content = new StreamReader(stream).ReadToEnd();
            
            Assert.Contains("v", content);
            Assert.Contains("f", content);
        }