def test_simple_triangle_binary(self):
        scene = Scene()
        mesh = Mesh('TestMesh')

        mesh._control_points.append(Vector4(0.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(1.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(0.0, 1.0, 0.0, 1.0))
        mesh.create_polygon(0, 1, 2)

        scene.root_node.create_child_node('TestNode').entity = mesh

        stream = io.BytesIO()
        options = GltfSaveOptions()
        options.binary_mode = True
        options.file_name = 'test.glb'

        from aspose.threed.formats.gltf import GltfExporter
        exporter = GltfExporter()
        exporter.export(scene, stream, options)

        stream.seek(0)
        content = stream.read()

        magic, version, length = struct.unpack('<4sII', content[:12])

        self.assertEqual(magic, b'glTF')
        self.assertEqual(version, 2)

        chunk_offset = 12
        json_chunk_length, json_chunk_type = struct.unpack('<II', content[chunk_offset:chunk_offset + 8])
        self.assertEqual(json_chunk_type, 0x4E4F534A)

        json_chunk = content[chunk_offset + 8:chunk_offset + 8 + json_chunk_length]
        gltf_data = json.loads(json_chunk.decode('utf-8'))

        self.assertEqual(gltf_data['asset']['version'], '2.0')
        self.assertIn('meshes', gltf_data)