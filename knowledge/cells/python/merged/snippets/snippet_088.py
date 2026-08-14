def test_create_excel_with_table():
    """
    Create a new Excel file with dummy data and add an Excel table.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("exceltable")
    
    output_path = examples_output_path("exceltable", "example_test_create_table.xlsx")
    
    # Create a new workbook
    print("Creating new workbook...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "SalesData"
    
    # Add dummy data for the table
    print("\nAdding dummy data for table...")
    # Add headers
    ws.cells["A1"].value = "Product"
    ws.cells["B1"].value = "Category"
    ws.cells["C1"].value = "Quantity"
    ws.cells["D1"].value = "Price"
    ws.cells["E1"].value = "Total"
    
    # Add data rows
    dummy_data = [
        ["Laptop", "Electronics", 5, 999.99, "=C2*D2"],
        ["Mouse", "Electronics", 20, 29.99, "=C3*D3"],
        ["Keyboard", "Electronics", 15, 79.99, "=C4*D4"],
        ["Monitor", "Electronics", 8, 299.99, "=C5*D5"],
        ["Headphones", "Electronics", 12, 149.99, "=C6*D6"],
        ["Desk Chair", "Furniture", 3, 249.99, "=C7*D7"],
        ["Desk Lamp", "Furniture", 10, 49.99, "=C8*D8"],
        ["Notebook", "Stationery", 50, 4.99, "=C9*D9"],
        ["Pen Set", "Stationery", 30, 12.99, "=C10*D10"],
        ["USB Cable", "Accessories", 25, 9.99, "=C11*D11"],
    ]
    
    for row_idx, row_data in enumerate(dummy_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(dummy_data)} rows of data")
    
    # Create a table from the dummy data (A1:E11)
    print("\nCreating Excel table from dummy data...")
    table = ws.tables.add(
        start_row=0,      # Row 1 (0-based)
        start_col=0,      # Column A (0-based)
        end_row=10,       # Row 11 (0-based)
        end_col=4,        # Column E (0-based)
        has_headers=True,
        name="SalesTable"
    )
    
    # Customize table style
    table.table_style_info.name = "TableStyleMedium9"
    table.table_style_info.show_row_stripes = True
    table.table_style_info.show_first_column = True
    table.table_style_info.show_last_column = False
    table.table_style_info.show_column_stripes = False
    
    print(f"Table created: name='{table.name}', ref='{table.ref}', columns={len(table.columns)}")
    for j, col in enumerate(table.columns):
        print(f"  Column {j}: name='{col.name}'")
    
    # Save the workbook
    print(f"\nSaving workbook to: {output_path}")
    wb.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path), f"Output file not created: {output_path}"
    
    # Verify the XML structure
    with zipfile.ZipFile(output_path) as zf:
        names = set(zf.namelist())
        # Check that table file exists
        assert "xl/tables/table1.xml" in names, "Missing table part"
        
        # Read and verify table XML
        table_xml = zf.read("xl/tables/table1.xml").decode("utf-8")
        
        # Verify table elements exist
        assert "<table" in table_xml, "Missing table element in table XML"
        
        # Verify table reference
        assert 'ref="A1:E11"' in table_xml, "Missing correct table reference"
        
        # Verify table name
        assert 'name="SalesTable"' in table_xml, "Missing table name"
        
        # Verify table style
        assert 'name="TableStyleMedium9"' in table_xml, "Missing table style"
        
        # Verify column names
        assert 'name="Product"' in table_xml, "Missing Product column"
        assert 'name="Category"' in table_xml, "Missing Category column"
        assert 'name="Quantity"' in table_xml, "Missing Quantity column"
        assert 'name="Price"' in table_xml, "Missing Price column"
        assert 'name="Total"' in table_xml, "Missing Total column"
    
    print(f"[OK] Successfully saved workbook with table")
    
    # Reload and verify
    print("\nReloading to verify...")
    wb_verify = Workbook(output_path)
    ws_verify = wb_verify.worksheets[0]
    print(f"[OK] Verified: {ws_verify.tables.count} table(s) in saved file")
    for i, table in enumerate(ws_verify.tables):
        print(f"  Table {i}: name='{table.name}', ref='{table.ref}', columns={len(table.columns)}")
        for j, col in enumerate(table.columns):
            print(f"    Column {j}: name='{col.name}'")
    
    return output_path