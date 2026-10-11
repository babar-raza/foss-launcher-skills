def test_per_triangle_materials(self):
        scene = Scene()
        options = self.plugin.create_load_options()
        
        model_content = '''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/2013/01">
  <resources>
    <color id="0" value="#FFFFFF" />
    <color id="1" value="#FF0000" />
    <object id="1" name="multicolor_cube">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/>
          <vertex x="10" y="0" z="0"/>
          <vertex x="10" y="10" z="0"/>
          <vertex x="0" y="10" z="0"/>
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" materialid="0"/>
          <triangle v1="0" v2="2" v3="3" materialid="1"/>
          <triangle v1="0" v2="3" v3="0" materialid="0"/>
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1"/>
  </build>
</model>'''
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('3D/3dmodel.model', model_content)
        
        zip_buffer.seek(0)
        scene.open(zip_buffer, options)
        
        self.assertEqual(len(scene.root_node.child_nodes), 1)
        multicolor_cube_node = scene.root_node.child_nodes[0]
        self.assertEqual(multicolor_cube_node.name, 'multicolor_cube')
        
        mesh = multicolor_cube_node.entity
        from aspose.threed.entities import VertexElementVertexColor
        vertex_color_element = None
        for elem in mesh._vertex_elements:
            if isinstance(elem, VertexElementVertexColor):
                vertex_color_element = elem
                break
        
        self.assertIsNotNone(vertex_color_element)
        colors = vertex_color_element.data
        self.assertEqual(len(colors), 3)
        
        self.assertEqual(colors[0].x, 1.0)
        self.assertEqual(colors[0].y, 1.0)
        self.assertEqual(colors[0].z, 1.0)
        
        self.assertEqual(colors[1].x, 1.0)
        self.assertEqual(colors[1].y, 0.0)
        self.assertEqual(colors[1].z, 0.0)
        
        self.assertEqual(colors[2].x, 1.0)
        self.assertEqual(colors[2].y, 1.0)
        self.assertEqual(colors[2].z, 1.0)