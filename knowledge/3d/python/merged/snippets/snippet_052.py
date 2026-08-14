def test_cylinder_to_mesh_should_create_mesh(self):
        """Test Cylinder.ToMesh() creates a valid mesh."""
        cylinder = Cylinder(5, 5, 20)
        mesh = cylinder.to_mesh()
        
        self.assertIsNotNone(mesh)
        self.assertGreater(len(mesh.control_points), 0)