def test_lambert_material_import(self):
        options = ColladaLoadOptions()

        file_path = os.path.join(os.path.dirname(__file__), '..', 'examples', 'collada', 'sphere.dae')
        
        if os.path.exists(file_path):
            scene = Scene()
            scene.open(file_path, options)

            self.assertIsNotNone(scene.root_node)

            sphere_node = None
            for node in scene.root_node.child_nodes:
                if 'sphere' in node.name.lower():
                    sphere_node = node
                    break

            self.assertIsNotNone(sphere_node)
            self.assertIsNotNone(sphere_node.material)
            self.assertEqual(type(sphere_node.material).__name__, 'LambertMaterial')

            material = sphere_node.material
            self.assertIsNotNone(material.diffuse_color)
            self.assertAlmostEqual(material.diffuse_color.x, 0.5, places=3)
            self.assertAlmostEqual(material.diffuse_color.y, 0.5, places=3)
            self.assertAlmostEqual(material.diffuse_color.z, 0.5, places=3)
        else:
            self.skipTest(f"File not found: {file_path}")