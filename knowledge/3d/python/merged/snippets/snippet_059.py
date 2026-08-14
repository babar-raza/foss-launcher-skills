def test_uv_loading(self):
        gltf_data = {
            "asset": {
                "version": "2.0",
                "generator": "test"
            },
            "scene": 0,
            "scenes": [
                {
                    "nodes": [0]
                }
            ],
            "nodes": [
                {
                    "name": "TestNode",
                    "mesh": 0
                }
            ],
            "meshes": [
                {
                    "name": "TestMesh",
                    "primitives": [
                        {
                            "attributes": {
                                "POSITION": 0,
                                "TEXCOORD_0": 1
                            },
                            "mode": 4
                        }
                    ]
                }
            ],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 3,
                    "type": "VEC3"
                },
                {
                    "bufferView": 1,
                    "componentType": 5126,
                    "count": 3,
                    "type": "VEC2"
                }
            ],
            "bufferViews": [
                {
                    "buffer": 0,
                    "byteOffset": 0,
                    "byteLength": 36
                },
                {
                    "buffer": 0,
                    "byteOffset": 36,
                    "byteLength": 24
                }
            ],
            "buffers": [
                {
                    "byteLength": 60,
                    "uri": "data:application/octet-stream;base64,AAAAAAAAAAAAAAAAAACAPwAAAAAAAAAAAAAAAAAAgD8AAAAAAAAAAAAAAAAAAIA/AAAAAAAAAAAAAIA/"
                }
            ]
        }

        scene = Scene()
        json_str = json.dumps(gltf_data)
        stream = io.BytesIO(json_str.encode('utf-8'))
        options = GltfLoadOptions()

        from aspose.threed.formats.gltf import GltfImporter
        importer = GltfImporter()
        importer.import_scene(scene, stream, options)

        self.assertEqual(len(scene.root_node.child_nodes), 1)
        node = scene.root_node.child_nodes[0]
        self.assertIsNotNone(node.entity)

        from aspose.threed.entities import VertexElementUV
        has_uvs = False
        for element in node.entity.vertex_elements:
            if isinstance(element, VertexElementUV):
                has_uvs = True
                self.assertEqual(len(element.data), 3)

        self.assertTrue(has_uvs, "Mesh should have VertexElementUV")