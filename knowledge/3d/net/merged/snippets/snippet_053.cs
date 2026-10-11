[Fact]
        public void Save3DSFile_ShouldHandleDuplicatedNames()
        {
            var scene = new Scene();
            var boxNode = scene.RootNode.CreateChildNode("Box");
            
            // Add a simple box mesh to the node
            var mesh = new Mesh("Box");
            mesh.ControlPoints.Add(new Vector4(0.0, 0.0, 0.0, 1.0));
            mesh.ControlPoints.Add(new Vector4(1.0, 0.0, 0.0, 1.0));
            mesh.ControlPoints.Add(new Vector4(1.0, 1.0, 0.0, 1.0));
            mesh.ControlPoints.Add(new Vector4(0.0, 1.0, 0.0, 1.0));
            mesh.ControlPoints.Add(new Vector4(0.0, 0.0, 1.0, 1.0));
            mesh.ControlPoints.Add(new Vector4(1.0, 0.0, 1.0, 1.0));
            mesh.ControlPoints.Add(new Vector4(1.0, 1.0, 1.0, 1.0));
            mesh.ControlPoints.Add(new Vector4(0.0, 1.0, 1.0, 1.0));
            
            boxNode.AddEntity(mesh);

            var tempFile = Path.Combine(Path.GetTempPath(), $"export-dupnames-{Guid.NewGuid()}.3ds");
            try
            {
                scene.Save(tempFile, FileFormat.Discreet3DS);

                Assert.True(File.Exists(tempFile), "Exported file should exist");

                var reOpenedScene = new Scene();
                reOpenedScene.Open(tempFile);

                int boxCount = 0;
                CountNodesByName(reOpenedScene.RootNode, "Box", ref boxCount);

                Assert.Equal(1, boxCount);
            }
            finally
            {
                if (File.Exists(tempFile))
                {
                    File.Delete(tempFile);
                }
            }
        }