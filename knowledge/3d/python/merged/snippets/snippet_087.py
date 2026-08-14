def test_mixed_triangle_and_quad_meshes(self):
        scene = Scene()
        
        mesh1 = Mesh("triangle_mesh")
        mesh1._control_points = [
            Vector4(0.0, 0.0, 0.0, 1.0),
            Vector4(1.0, 0.0, 0.0, 1.0),
            Vector4(1.0, 1.0, 0.0, 1.0),
        ]
        mesh1.create_polygon(0, 1, 2)
        
        node1 = Node("node1")
        node1.entity = mesh1
        node1.parent_node = scene.root_node
        
        mesh2 = Mesh("quad_mesh")
        mesh2._control_points = [
            Vector4(2.0, 0.0, 0.0, 1.0),
            Vector4(3.0, 0.0, 0.0, 1.0),
            Vector4(3.0, 1.0, 0.0, 1.0),
            Vector4(2.0, 1.0, 0.0, 1.0),
        ]
        mesh2.create_polygon(0, 1, 2, 3)
        
        node2 = Node("node2")
        node2.entity = mesh2
        node2.parent_node = scene.root_node
        
        stream = io.StringIO()
        options = StlSaveOptions()
        options.binary_mode = False
        
        exporter = StlExporter()
        exporter.export(scene, stream, options)
        
        content = stream.getvalue()
        facet_count = content.count("facet normal")
        self.assertEqual(facet_count, 3)