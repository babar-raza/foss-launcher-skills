def test_simple_triangle_export(self):
        scene = Scene()
        mesh = Mesh('TestMesh')

        mesh._control_points.append(Vector4(0.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(1.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(0.0, 1.0, 0.0, 1.0))
        mesh.create_polygon(0, 1, 2)

        scene.root_node.create_child_node('TestNode').entity = mesh

        stream = io.BytesIO()
        options = ColladaSaveOptions()
        options.file_name = 'test.dae'

        from aspose.threed.formats.collada.ColladaExporter import ColladaExporter
        exporter = ColladaExporter()
        exporter.export(scene, stream, options)

        stream.seek(0)
        content = stream.read().decode('utf-8')

        root = ET.fromstring(content)
        self.assertEqual(root.tag, '{http://www.collada.org/2005/11/COLLADASchema}COLLADA')
        self.assertEqual(root.get('version'), '1.4.1')

        asset = root.find('{http://www.collada.org/2005/11/COLLADASchema}asset')
        self.assertIsNotNone(asset)

        library_geometries = root.find('{http://www.collada.org/2005/11/COLLADASchema}library_geometries')
        self.assertIsNotNone(library_geometries)

        library_visual_scenes = root.find('{http://www.collada.org/2005/11/COLLADASchema}library_visual_scenes')
        self.assertIsNotNone(library_visual_scenes)