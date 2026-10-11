[Fact]
        public void Load3DSFile_ShouldLoadScene()
        {
            var testDataPath = GetTestDataPath();
            var testFile = Path.Combine(testDataPath, "3ds", "test.3DS");
            
            Assert.True(File.Exists(testFile), $"Test file not found: {testFile}");
            
            var scene = new Scene();
            scene.Open(testFile);
            
            Assert.NotNull(scene);
            Assert.NotNull(scene.RootNode);
            Assert.NotNull(scene.RootNode.ChildNodes);
            
            Console.WriteLine($"Scene loaded. Root nodes: {scene.RootNode.ChildNodes.Count}");
            
            foreach (var node in scene.RootNode.ChildNodes)
            {
                Console.WriteLine($"  Node: {node.Name}, Entities: {node.Entities.Count}");
                foreach (var entity in node.Entities)
                {
                    Console.WriteLine($"    Entity: {entity.GetType().Name}");
                }
            }
            
            Assert.True(scene.RootNode.ChildNodes.Count > 0, "Scene should have at least one child node");
        }