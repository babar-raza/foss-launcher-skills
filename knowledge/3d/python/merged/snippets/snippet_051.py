def test_box_to_mesh_should_create_mesh(self):
        """Test Box.ToMesh() creates a valid mesh."""
        box = Box(10, 20, 30)
        mesh = box.to_mesh()
        
        self.assertIsNotNone(mesh)
        self.assertEqual(8, len(mesh.control_points))