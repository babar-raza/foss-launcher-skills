def test_export_multiple_materials(self):
        scene = Scene()
        options = self.plugin.create_save_options()
        options.enable_compression = False
        
        for i, color in enumerate([(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]):
            mesh = Mesh(f'cube_{i}')
            
            mesh._control_points.append(Vector4(0, 0, 0, 1))
            mesh._control_points.append(Vector4(1, 0, 0, 1))
            mesh._control_points.append(Vector4(1, 1, 0, 1))
            mesh._control_points.append(Vector4(0, 1, 0, 1))
            
            mesh.create_polygon(0, 1, 2)
            mesh.create_polygon(0, 2, 3)
            
            node = Node(f'cube_{i}')
            node.entity = mesh
            node.parent_node = scene.root_node
            
            material = LambertMaterial(f'Material_{i}')
            material.diffuse_color = Vector3(color[0], color[1], color[2])
            node.material = material
        
        output_buffer = io.BytesIO()
        scene.save(output_buffer, options)
        
        output_buffer.seek(0)
        
        zip_file = zipfile.ZipFile(output_buffer, 'r')
        model_content = zip_file.read('3D/3dmodel.model').decode('utf-8')
        zip_file.close()
        
        root = ET.fromstring(model_content)
        
        resources = root.find('{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}resources')
        self.assertIsNotNone(resources)
        
        base_materials = resources.find('{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}basematerials')
        self.assertIsNotNone(base_materials)
        
        base_elems = base_materials.findall('{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}base')
        self.assertEqual(len(base_elems), 3)