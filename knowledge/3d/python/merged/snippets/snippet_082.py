def test_material_import_from_sample():
    print("="*70)
    print("TEST: Material Import from Sample 3MF Files")
    print("="*70)
    
    sample_file = '/home/lexchou/workspace/aspose/3d.org/examples/3mf/dodeca_chain_loop_color.3mf'
    
    scene = Scene()
    scene.open(sample_file, ThreeMfLoadOptions())
    
    print(f"\n✓ Scene loaded successfully")
    print(f"  Root node has {len(scene.root_node.child_nodes)} children")
    
    materials_found = 0
    
    return materials_found > 0