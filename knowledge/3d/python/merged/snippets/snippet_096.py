def test_disable_materials(self):
        obj_content = """# Test disable materials
o TestMesh
usemtl MyMaterial
v 0.0 0.0 0.0
v 1.0 0.0 0.0
f 1 2 3
"""
        scene = Scene()
        stream = io.StringIO(obj_content)
        options = ObjLoadOptions()
        options.enable_materials = False
        
        importer = ObjImporter()
        importer.import_scene(scene, stream, options)
        
        if len(scene.root_node.child_nodes) > 0:
            node = scene.root_node.child_nodes[0]
            self.assertIsNone(node.material)
        else:
            self.fail("No child nodes created")