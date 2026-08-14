def test_pyramid_to_mesh_should_create_mesh(self):
        """Test Pyramid.ToMesh() creates a valid mesh."""
        pyramid = Pyramid(10, 10, 20)
        mesh = pyramid.to_mesh()
        
        self.assertIsNotNone(mesh)
        self.assertGreaterEqual(len(mesh.control_points), 4)