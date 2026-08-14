def test_export_with_uvs(self):
        from aspose.threed.entities import VertexElementUV
        from aspose.threed.utilities.FVector4 import FVector4

        scene = Scene()
        mesh = Mesh('TestMesh')

        mesh._control_points.append(Vector4(0.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(1.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(0.0, 1.0, 0.0, 1.0))
        mesh.create_polygon(0, 1, 2)

        uv_element = VertexElementUV()
        uv_element._data.extend([
            FVector4(0.0, 0.0, 0.0, 0.0),
            FVector4(1.0, 0.0, 0.0, 0.0),
            FVector4(0.0, 1.0, 0.0, 0.0)
        ])
        mesh._vertex_elements.append(uv_element)

        scene.root_node.create_child_node('TestNode').entity = mesh

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

        self.assertGreater(len(gltf_data['meshes']), 0)
        mesh_data = gltf_data['meshes'][0]
        self.assertIn('primitives', mesh_data)
        self.assertIn('TEXCOORD_0', mesh_data['primitives'][0]['attributes'])