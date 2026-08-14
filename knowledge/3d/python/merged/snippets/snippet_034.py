def test_phong_material_import(self):
        options = ColladaLoadOptions()

        file_path = os.path.join(os.path.dirname(__file__), '..', 'examples', 'collada', 'cube_triangulate.dae')
        
        if os.path.exists(file_path):
            scene = Scene()
            scene.open(file_path, options)

            self.assertIsNotNone(scene.root_node)

            box_node = None
            for node in scene.root_node.child_nodes:
                if node.name == 'Box':
                    box_node = node
                    break

            self.assertIsNotNone(box_node)
            self.assertIsNotNone(box_node.material)
            self.assertEqual(type(box_node.material).__name__, 'PhongMaterial')

            material = box_node.material
            self.assertIsNotNone(material.diffuse_color)
            self.assertAlmostEqual(material.diffuse_color.x, 0.137255, places=5)
            self.assertAlmostEqual(material.diffuse_color.y, 0.403922, places=5)
            self.assertAlmostEqual(material.diffuse_color.z, 0.870588, places=5)

            self.assertIsNotNone(material.specular_color)
            self.assertIsNotNone(material.emissive_color)
            self.assertIsNotNone(material.ambient_color)

            self.assertAlmostEqual(material.shininess, 16.0, places=1)
            self.assertAlmostEqual(material.transparency, 0.0, places=1)
        else:
            self.skipTest(f"File not found: {file_path}")