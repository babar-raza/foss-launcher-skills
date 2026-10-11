def test_torus_to_mesh_should_create_mesh(self):
        """Test Torus.ToMesh() creates a valid mesh."""
        torus = Torus(10, 3)
        mesh = torus.to_mesh()
        
        self.assertIsNotNone(mesh)
        self.assertGreater(len(mesh.control_points), 0)