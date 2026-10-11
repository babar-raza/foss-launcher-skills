def test_materials_always_loaded(self):
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
        else:
            self.skipTest(f"File not found: {file_path}")