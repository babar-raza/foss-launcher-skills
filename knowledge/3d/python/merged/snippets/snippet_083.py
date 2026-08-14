def test_simple_cube_with_material():
    print("\n" + "="*70)
    print("TEST: Simple Scene with Material")
    print("="*70)
    
    import io
    import xml.etree.ElementTree as ET
    from aspose.threed.formats import ThreeMfSaveOptions, ThreeMfLoadOptions
    
    scene = Scene()
    from aspose.threed.shading import PbrMaterial
    from aspose.threed.entities import Mesh
    from aspose.threed.utilities import Vector3
    
    mat = PbrMaterial('test_material')
    mat.albedo = Vector3(1.0, 0.0, 0.0)
    
    mesh = Mesh('cube')
    mesh._control_points = [
        Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(1, 1, 0), Vector3(0, 1, 0),
        Vector3(0, 0, 1), Vector3(1, 0, 1), Vector3(1, 1, 1), Vector3(0, 1, 1)
    ]
    for indices in [(0,1,2), (0,2,3), (4,7,6), (4,6,5), (0,4,5), (0,5,1), (2,6,7), (2,7,3), (0,3,7), (0,7,4), (1,5,6), (1,6,2)]:
        mesh.create_polygon(*indices)
    
    node = scene.root_node.create_child_node('cube')
    node.entity = mesh
    node.material = mat
    
    print(f"\n✓ Created scene with material")
    print(f"  Node: {node.name}")
    print(f"  Mesh: {len(mesh._control_points)} vertices, {mesh.polygon_count} polygons")
    print(f"  Material: {mat.name}, albedo=({mat.albedo.x:.1f}, {mat.albedo.y:.1f}, {mat.albedo.z:.1f})")
    
    output = io.BytesIO()
    scene.save(output, ThreeMfSaveOptions())
    
    print(f"\n✓ Scene exported to 3MF")
    print(f"  Output size: {len(output.getvalue())} bytes")
    
    return True