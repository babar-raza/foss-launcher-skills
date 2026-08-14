[Fact]
        public void SaveSceneToFbx_ShouldCreateValidBinaryFile()
        {
            var scene = new Scene();
            var box = new Box(2, 2, 2);
            var node = scene.RootNode.CreateChildNode("BoxNode", box);

            var outputFile = Path.Combine(Path.GetTempPath(), "test_output.fbx");             try
             {
                                   var options = new Fmt.FbxSaveOptions(FileFormat.FBX7700Binary);
                 scene.Save(outputFile, options);
                Assert.True(File.Exists(outputFile));
                var content = File.ReadAllBytes(outputFile);
                
                Assert.Contains("Kaydara FBX Binary", System.Text.Encoding.ASCII.GetString(content, 0, Math.Min(50, content.Length)));
            }
            finally
            {
                if (File.Exists(outputFile))
                {
                    File.Delete(outputFile);
                }
            }
        }