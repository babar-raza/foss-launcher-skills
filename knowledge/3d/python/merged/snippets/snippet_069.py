def test_export_with_transparent_material(self):
        scene = Scene()
        mesh = Mesh('TestMesh')

        mesh._control_points.append(Vector4(0.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(1.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(0.0, 1.0, 0.0, 1.0))
        mesh.create_polygon(0, 1, 2)

        material = PbrMaterial('TransparentMaterial')
        material.albedo = Vector3(1.0, 1.0, 1.0)
        material.transparency = 0.6

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
        material_data = gltf_data['materials'][0]
        self.assertEqual(material_data['alphaMode'], 'MASK')
        self.assertEqual(material_data['alphaCutoff'], 0.4)