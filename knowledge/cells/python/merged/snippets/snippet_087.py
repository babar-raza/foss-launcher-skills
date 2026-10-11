def test_create_all_charts():
    """Create all supported chart types in one test."""
    # Ensure output directory exists
    ensure_examples_output_dir("progcharts")
    
    print("\n=== Creating All Supported Chart Types ===\n")
    print("Note: Box and Whisker chart creation is not yet implemented.\n")
    
    test_create_line_chart()
    test_create_bar_chart()
    test_create_pie_chart()
    test_create_area_chart()
    # test_create_box_whisker_chart()
    test_create_waterfall_chart()
    test_create_scatter_chart()
    test_create_combo_chart()
    test_create_stock_chart()
    test_create_surface_chart()
    test_create_radar_chart()
    test_create_treemap_chart()
    test_create_sunburst_chart()
    test_create_histogram_chart()
    test_create_funnel_chart()
    test_create_map_chart()
    
    print("\n=== All Supported Charts Created Successfully ===\n")
    print("Output files saved to: examples/outputfiles/progcharts/")