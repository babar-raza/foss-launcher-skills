def test_export_with_material(self):
        scene = Scene()
        mesh = Mesh('TestMesh')

        mesh._control_points.append(Vector4(0.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(1.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(0.0, 1.0, 0.0, 1.0))
        mesh.create_polygon(0, 1, 2)

        albedo = Vector3(0.8, 0.2, 0.3)
        material = PbrMaterial('RedMaterial', albedo)
        material.metallic_factor = 0.5
        material.roughness_factor = 0.7

        node = scene.root_node.create_child_node('TestNode')
        node.entity = mesh
        node.material = material

        stream = io.BytesIO()
        options = GltfSaveOptions()
        options.binary_mode = False
        options.file_name = 'test.gltf'

        from aspose.threed.formats.gltf import GltfExporter
        exporter = GltfExporter()
        exporter.export(scene, stream, options)

        stream.seek(0)
        content = stream.read()
        gltf_data = json.loads(content.decode('utf-8'))

        self.assertIn('materials', gltf_data)
        self.assertEqual(len(gltf_data['materials']), 1)

        material_data = gltf_data['materials'][0]
        self.assertEqual(material_data['name'], 'RedMaterial')
        self.assertIn('pbrMetallicRoughness', material_data)

        pbr_data = material_data['pbrMetallicRoughness']
        self.assertEqual(pbr_data['baseColorFactor'], [0.8, 0.2, 0.3, 1.0])
        self.assertEqual(pbr_data['metallicFactor'], 0.5)
        self.assertEqual(pbr_data['roughnessFactor'], 0.7)

        self.assertIn('meshes', gltf_data)
        mesh_data = gltf_data['meshes'][0]
        self.assertIn('primitives', mesh_data)
        primitive_data = mesh_data['primitives'][0]
        self.assertIn('material', primitive_data)
        self.assertEqual(primitive_data['material'], 0)