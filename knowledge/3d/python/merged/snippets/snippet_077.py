def test_gltf_binary_format(self):
        scene = Scene()
        stream = io.BytesIO()

        magic = b'glTF'
        version = 2
        total_length = 12 + 8 + len(b'{"asset":{"version":"2.0"}}') + 8 + len(b'')

        stream.write(struct.pack('<4sII', magic, version, total_length))

        json_chunk = b'{"asset":{"version":"2.0"},"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"name":"TestNode"}]}'
        json_chunk_type = 0x4E4F534A
        json_chunk_length = len(json_chunk)

        stream.write(struct.pack('<II', json_chunk_length, json_chunk_type))
        stream.write(json_chunk)

        binary_chunk_type = 0x004E4942
        binary_chunk_length = 0

        stream.write(struct.pack('<II', binary_chunk_length, binary_chunk_type))

        stream.seek(0)
        options = GltfLoadOptions()

        try:
            from aspose.threed.formats.gltf import GltfImporter
            importer = GltfImporter()
            importer.import_scene(scene, stream, options)

            self.assertEqual(len(scene.root_node.child_nodes), 1)
            node = scene.root_node.child_nodes[0]
            self.assertEqual(node.name, 'TestNode')
        except Exception as e:
            self.fail(f"Failed to import binary glTF: {e}")