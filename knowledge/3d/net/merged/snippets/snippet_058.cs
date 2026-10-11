[Fact]
        public void Load3DSFile_ShouldLoadMesh()
        {
            var testDataPath = GetTestDataPath();
            var testFile = Path.Combine(testDataPath, "3ds", "cube.3DS");
            
            var scene = new Scene();
            scene.Open(testFile);
            
            // Check that we have at least one node with a mesh
            Mesh? foundMesh = null;
            foreach (var node in scene.RootNode.ChildNodes)
            {
                Console.WriteLine($"Node: {node.Name}, Entities: {node.Entities.Count}");
                foreach (var entity in node.Entities)
                {
                    Console.WriteLine($"  Entity: {entity.GetType().Name}");
                    if (entity is Mesh m)
                    {
                        foundMesh = m;
                        break;
                    }
                }
                if (foundMesh != null) break;
            }
            
            Assert.NotNull(foundMesh);
            Assert.True(foundMesh != null, "Should have at least one node with a Mesh entity");
            Assert.True(foundMesh.ControlPoints.Count > 0, "Mesh should have control points");
            Assert.True(foundMesh.PolygonCount > 0, "Mesh should have faces");
        }