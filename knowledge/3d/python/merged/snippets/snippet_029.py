def test_export_lambert_material(self):
        scene = Scene()
        mesh = Mesh('TestMesh')

        mesh._control_points.append(Vector4(0.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(1.0, 0.0, 0.0, 1.0))
        mesh._control_points.append(Vector4(0.0, 1.0, 0.0, 1.0))
        mesh.create_polygon(0, 1, 2)

        material = LambertMaterial('BlueMaterial')
        material.diffuse_color = Vector3(0.0, 0.0, 1.0)

        node = scene.root_node.create_child_node('TestNode')
        node.entity = mesh
        node.material = material

        stream = io.BytesIO()
        options = ColladaSaveOptions()
        options.file_name = 'test.dae'

        from aspose.threed.formats.collada.ColladaExporter import ColladaExporter
        exporter = ColladaExporter()
        exporter.export(scene, stream, options)

        stream.seek(0)
        content = stream.read().decode('utf-8')

        root = ET.fromstring(content)

        library_effects = root.find('{http://www.collada.org/2005/11/COLLADASchema}library_effects')
        self.assertIsNotNone(library_effects)

        effect = library_effects.find('{http://www.collada.org/2005/11/COLLADASchema}effect')
        self.assertIsNotNone(effect)

        profile_common = effect.find('{http://www.collada.org/2005/11/COLLADASchema}profile_COMMON')
        self.assertIsNotNone(profile_common)

        technique = profile_common.find('{http://www.collada.org/2005/11/COLLADASchema}technique')
        self.assertIsNotNone(technique)

        lambert = technique.find('{http://www.collada.org/2005/11/COLLADASchema}lambert')
        self.assertIsNotNone(lambert)