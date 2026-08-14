def test_mesh_to_mesh_should_return_same_mesh(self):
        """Test Mesh.ToMesh() returns the same mesh."""
        mesh = Mesh()
        mesh.create_polygon([0, 1, 2])
        
        result = mesh.to_mesh()
        
        self.assertIsNotNone(result)
        self.assertEqual(mesh, result)