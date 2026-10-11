def test_export_multiple_meshes(self):
        scene = Scene()
        
        mesh1 = Mesh("mesh1")
        mesh1._control_points = [
            Vector4(0.0, 0.0, 0.0, 1.0),
            Vector4(1.0, 0.0, 0.0, 1.0),
            Vector4(1.0, 1.0, 0.0, 1.0),
        ]
        mesh1.create_polygon(0, 1, 2)
        
        node1 = Node("node1")
        node1.entity = mesh1
        node1.parent_node = scene.root_node
        
        mesh2 = Mesh("mesh2")
        mesh2._control_points = [
            Vector4(2.0, 0.0, 0.0, 1.0),
            Vector4(3.0, 0.0, 0.0, 1.0),
            Vector4(3.0, 1.0, 0.0, 1.0),
        ]
        mesh2.create_polygon(0, 1, 2)
        
        node2 = Node("node2")
        node2.entity = mesh2
        node2.parent_node = scene.root_node
        
        mesh3 = Mesh("mesh3")
        mesh3._control_points = [
            Vector4(4.0, 0.0, 0.0, 1.0),
            Vector4(5.0, 0.0, 0.0, 1.0),
            Vector4(5.0, 1.0, 0.0, 1.0),
        ]
        mesh3.create_polygon(0, 1, 2)
        
        node3 = Node("node3")
        node3.entity = mesh3
        node3.parent_node = scene.root_node
        
        stream = io.StringIO()
        options = StlSaveOptions()
        options.binary_mode = False
        
        exporter = StlExporter()
        exporter.export(scene, stream, options)
        
        content = stream.getvalue()
        facet_count = content.count("facet normal")
        self.assertEqual(facet_count, 3)