def test_flip_tex_coord_v(self):
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
            FVector4(0.0, 0.5, 0.0, 0.0),
            FVector4(1.0, 0.5, 0.0, 0.0),
            FVector4(0.0, 1.0, 0.0, 0.0)
        ])
        mesh._vertex_elements.append(uv_element)

        scene.root_node.create_child_node('TestNode').entity = mesh

        from aspose.threed.formats.gltf import GltfExporter
        exporter = GltfExporter()

        stream1 = io.BytesIO()
        options1 = GltfSaveOptions()
        options1.binary_mode = False
        options1.flip_tex_coord_v = True
        options1.file_name = 'test1.gltf'

        exporter.export(scene, stream1, options1)

        stream2 = io.BytesIO()
        options2 = GltfSaveOptions()
        options2.binary_mode = False
        options2.flip_tex_coord_v = False
        options2.file_name = 'test2.gltf'

        exporter.export(scene, stream2, options2)

        self.assertTrue(True)