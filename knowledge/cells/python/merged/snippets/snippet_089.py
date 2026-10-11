def test_create_multiple_tables():
    """
    Create a new Excel file with multiple tables in different ranges.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("exceltable")
    
    output_path = examples_output_path("exceltable", "example_test_create_multiple_tables.xlsx")
    
    # Create a new workbook
    print("\nCreating new workbook with multiple tables...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    ws.name = "MultipleTables"
    
    # Add first table data (Employees)
    print("\nAdding first table data (Employees)...")
    ws.cells["A1"].value = "Employee ID"
    ws.cells["B1"].value = "Name"
    ws.cells["C1"].value = "Department"
    ws.cells["D1"].value = "Salary"
    
    employee_data = [
        ["E001", "John Smith", "Engineering", 85000],
        ["E002", "Jane Doe", "Marketing", 75000],
        ["E003", "Bob Johnson", "Engineering", 90000],
        ["E004", "Alice Brown", "HR", 65000],
        ["E005", "Charlie Wilson", "Finance", 80000],
    ]
    
    for row_idx, row_data in enumerate(employee_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    # Create first table
    table1 = ws.tables.add(
        start_row=0, start_col=0, end_row=5, end_col=3,
        has_headers=True, name="EmployeesTable"
    )
    table1.table_style_info.name = "TableStyleMedium7"
    table1.table_style_info.show_row_stripes = True
    
    print(f"First table created: name='{table1.name}', ref='{table1.ref}'")
    
    # Add second table data (Projects) - starting at row 8
    print("\nAdding second table data (Projects)...")
    ws.cells["A8"].value = "Project ID"
    ws.cells["B8"].value = "Project Name"
    ws.cells["C8"].value = "Status"
    ws.cells["D8"].value = "Budget"
    
    project_data = [
        ["P001", "Website Redesign", "In Progress", 50000],
        ["P002", "Mobile App", "Planning", 75000],
        ["P003", "Database Migration", "Completed", 30000],
        ["P004", "Cloud Integration", "On Hold", 60000],
    ]
    
    for row_idx, row_data in enumerate(project_data, start=9):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    # Create second table
    table2 = ws.tables.add(
        start_row=7, start_col=0, end_row=11, end_col=3,
        has_headers=True, name="ProjectsTable"
    )
    table2.table_style_info.name = "TableStyleMedium11"
    table2.table_style_info.show_row_stripes = True
    
    print(f"Second table created: name='{table2.name}', ref='{table2.ref}'")
    
    # Save the workbook
    print(f"\nSaving workbook to: {output_path}")
    wb.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path), f"Output file not created: {output_path}"
    
    # Verify the XML structure
    with zipfile.ZipFile(output_path) as zf:
        names = set(zf.namelist())
        # Check that both table files exist
        assert "xl/tables/table1.xml" in names, "Missing first table part"
        assert "xl/tables/table2.xml" in names, "Missing second table part"
        
        # Read and verify table XMLs
        table1_xml = zf.read("xl/tables/table1.xml").decode("utf-8")
        table2_xml = zf.read("xl/tables/table2.xml").decode("utf-8")
        
        # Verify first table
        assert 'name="EmployeesTable"' in table1_xml, "Missing first table name"
        assert 'ref="A1:D6"' in table1_xml, "Missing correct reference in first table"
        
        # Verify second table
        assert 'name="ProjectsTable"' in table2_xml, "Missing second table name"
        assert 'ref="A8:D12"' in table2_xml, "Missing correct reference in second table"
    
    print(f"[OK] Successfully saved workbook with {ws.tables.count} table(s)")
    
    # Reload and verify
    print("\nReloading to verify...")
    wb_verify = Workbook(output_path)
    ws_verify = wb_verify.worksheets[0]
    print(f"[OK] Verified: {ws_verify.tables.count} table(s) in saved file")
    for i, table in enumerate(ws_verify.tables):
        print(f"  Table {i}: name='{table.name}', ref='{table.ref}', columns={len(table.columns)}")
    
    return output_path