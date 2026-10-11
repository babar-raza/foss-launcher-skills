def test_smoothing_groups(self):
        obj_content = """# Test smoothing groups
o TestMesh
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4

s 1
v 2.0 0.0 0.0
v 3.0 0.0 0.0
f 5 6 7 8
"""
        scene = Scene()
        stream = io.StringIO(obj_content)
        options = ObjLoadOptions()
        
        importer = ObjImporter()
        importer.import_scene(scene, stream, options)
        
        self.assertGreater(len(scene.root_node.child_nodes), 0)