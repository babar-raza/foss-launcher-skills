def test_groups(self):
        obj_content = """# Groups
o MyObject
g Group1
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4

g Group2
v 2.0 0.0 0.0
v 3.0 0.0 0.0
v 3.0 1.0 0.0
v 2.0 1.0 0.0
f 5 6 7 8
"""
        scene = Scene()
        stream = io.StringIO(obj_content)
        options = ObjLoadOptions()
        options.file_name = "test.obj"
        
        importer = ObjImporter()
        importer.import_scene(scene, stream, options)
        
        self.assertGreater(len(scene.root_node.child_nodes), 0)