def test_sphere_to_mesh_should_create_mesh(self):
        """Test Sphere.ToMesh() creates a valid mesh."""
        sphere = Sphere(10, 32, 16)
        mesh = sphere.to_mesh()
        
        self.assertIsNotNone(mesh)
        self.assertGreater(len(mesh.control_points), 0)