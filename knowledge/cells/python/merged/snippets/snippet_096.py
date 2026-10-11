def test_create_column_sparklines():
    """
    Create a new Excel file with dummy data and add column sparklines.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("createsparkline")
    
    output_path = examples_output_path("createsparkline", "example_test_create_column_sparklines.xlsx")
    
    # Create a new workbook
    print("\nCreating new workbook for column sparklines...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "ColumnSparklines"
    
    # Add dummy data for column sparklines
    print("\nAdding dummy data...")
    # Add headers
    ws.cells["A1"].value = "Product"
    ws.cells["B1"].value = "Q1"
    ws.cells["C1"].value = "Q2"
    ws.cells["D1"].value = "Q3"
    ws.cells["E1"].value = "Q4"
    ws.cells["F1"].value = "Quarterly"
    
    # Add data rows
    dummy_data = [
        ["Product A", 150, 200, 180, 220],
        ["Product B", 120, 140, 160, 190],
        ["Product C", 180, 170, 150, 200],
        ["Product D", 90, 110, 130, 145],
        ["Product E", 200, 210, 190, 230],
    ]
    
    for row_idx, row_data in enumerate(dummy_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(dummy_data)} rows of data")
    
    # Add column sparklines
    print("\nAdding column sparklines...")
    
    # Create a sparkline group for column sparklines
    sparkline_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.COLUMN,
        data_range=f"{ws.name}!B2:E6",
        is_vertical=False,
        location_range="F2:F6"
    )
    
    # Customize sparkline appearance
    sparkline_group.color_series = "FFC000"  # Orange
    sparkline_group.show_high_point = True
    sparkline_group.show_low_point = True
    sparkline_group.color_high = "00B050"  # Green for high point
    sparkline_group.color_low = "C00000"   # Dark red for low point
    
    print(f"Added {sparkline_group.count} column sparklines")
    
    # Save the workbook
    print(f"\nSaving workbook to: {output_path}")
    wb.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path), f"Output file not created: {output_path}"
    
    # Verify the XML structure
    with zipfile.ZipFile(output_path) as zf:
        worksheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        
        # Verify sparkline type is column
        assert 'type="column"' in worksheet_xml, "Missing column type attribute"
        
        # Verify colors
        assert "FFC000" in worksheet_xml, "Missing series color"
        assert "00B050" in worksheet_xml, "Missing high point color"
        assert "C00000" in worksheet_xml, "Missing low point color"
    
    print(f"[OK] Successfully saved workbook with {sparkline_group.count} column sparklines")
    
    # Reload and verify
    print("\nReloading to verify...")
    wb_verify = Workbook(output_path)
    ws_verify = wb_verify.worksheets[0]
    print(f"[OK] Verified: {ws_verify.sparkline_groups.count} sparkline group(s) in saved file")
    
    return output_path