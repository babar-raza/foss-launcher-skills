def test_scale(self):
        obj_content = """# Test scaling
o TestMesh
v 1.0 1.0 1.0
v 2.0 2.0 2.0
v 3.0 2.0 2.0
f 1 2 3
"""
        scene = Scene()
        stream = io.StringIO(obj_content)
        options = ObjLoadOptions()
        options.scale = 2.0
        
        importer = ObjImporter()
        importer.import_scene(scene, stream, options)
        
        self.assertGreater(len(scene.root_node.child_nodes), 0)
        
        node = scene.root_node.child_nodes[0]
        self.assertIsNotNone(node.entity)
        
        mesh = node.entity
        first_point = mesh.control_points[0]
        self.assertAlmostEqual(first_point.x, 2.0)
        self.assertAlmostEqual(first_point.y, 2.0)
        self.assertAlmostEqual(first_point.z, 2.0)