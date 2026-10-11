[Fact]
        public void SaveSceneToStreamStl_ShouldCreateValidOutput()
        {
            var scene = new Scene();
            var box = new Box(2, 2, 2);
            scene.RootNode.CreateChildNode("BoxNode", box);

            using var stream = new MemoryStream();
            var options = new Fmt.StlSaveOptions();
            scene.Save(stream, options);

            stream.Seek(0, SeekOrigin.Begin);
            var content = stream.ToArray();
            
            Assert.True(content.Length > 84);
        }