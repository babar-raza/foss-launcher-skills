def test_create_approval_workflow():
    """
    Create a new Excel file with an approval workflow using shapes.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("createshape")
    
    output_path = examples_output_path("createshape", "example_test_create_approval_workflow.xlsx")
    
    # Create a new workbook
    print("\nCreating new workbook for approval workflow...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "ApprovalWorkflow"
    
    # Add dummy data for the approval workflow
    print("\nAdding approval workflow data...")
    # Add headers
    ws.cells["A1"].value = "Request ID"
    ws.cells["B1"].value = "Requester"
    ws.cells["C1"].value = "Type"
    ws.cells["D1"].value = "Amount"
    ws.cells["E1"].value = "Status"
    
    # Add data rows
    approval_data = [
        ["REQ001", "Alice", "Expense", 1500.00, "Pending Manager"],
        ["REQ002", "Bob", "Purchase", 5000.00, "Pending Finance"],
        ["REQ003", "Charlie", "Expense", 250.00, "Approved"],
        ["REQ004", "David", "Purchase", 12000.00, "Pending Director"],
        ["REQ005", "Eve", "Expense", 800.00, "Rejected"],
    ]
    
    for row_idx, row_data in enumerate(approval_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(approval_data)} rows of approval data")
    
    # Add approval workflow shapes
    print("\nAdding approval workflow shapes...")
    
    # Shape 1: Request Submission (Oval) - Purple
    request_shape = ws.shapes.add(
        MsoDrawingType.OVAL,
        upper_left_row=1,
        upper_left_column=7,
        lower_right_row=4,
        lower_right_column=10
    )
    request_shape.name = "Request"
    request_shape.text = "Submit\nRequest"
    request_shape.fill.fill_type = FillType.SOLID
    request_shape.fill.fore_color = "DDA0DD"  # Plum
    request_shape.line.is_visible = True
    request_shape.line.color = "800080"  # Purple
    request_shape.line.weight = 12700  # 1 pt
    request_shape.font.name = "Arial"
    request_shape.font.size = 11.0
    request_shape.font.bold = True
    request_shape.text_horizontal_alignment = TextAlignmentType.CENTER
    request_shape.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {request_shape.name} (Oval)")
    
    # Shape 2: Arrow 1 (Right Arrow)
    arrow1 = ws.shapes.add(
        MsoDrawingType.RIGHT_ARROW,
        upper_left_row=2,
        upper_left_column=10,
        lower_right_row=4,
        lower_right_column=12
    )
    arrow1.name = "Arrow1"
    arrow1.text = "→"
    arrow1.fill.fill_type = FillType.SOLID
    arrow1.fill.fore_color = "D3D3D3"
    arrow1.line.is_visible = True
    arrow1.line.color = "696969"
    arrow1.line.weight = 9525
    arrow1.font.name = "Arial"
    arrow1.font.size = 16.0
    arrow1.text_horizontal_alignment = TextAlignmentType.CENTER
    arrow1.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {arrow1.name} (Right Arrow)")
    
    # Shape 3: Manager Approval (Rectangle) - Blue
    manager_shape = ws.shapes.add(
        MsoDrawingType.RECTANGLE,
        upper_left_row=1,
        upper_left_column=12,
        lower_right_row=4,
        lower_right_column=15
    )
    manager_shape.name = "Manager"
    manager_shape.text = "Manager\nApproval"
    manager_shape.fill.fill_type = FillType.SOLID
    manager_shape.fill.fore_color = "4169E1"  # Royal blue
    manager_shape.line.is_visible = True
    manager_shape.line.color = "000080"  # Navy
    manager_shape.line.weight = 12700
    manager_shape.font.name = "Arial"
    manager_shape.font.size = 11.0
    manager_shape.font.bold = True
    manager_shape.font.color = "FFFFFF"  # White text
    manager_shape.text_horizontal_alignment = TextAlignmentType.CENTER
    manager_shape.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {manager_shape.name} (Rectangle)")
    
    # Shape 4: Arrow 2 (Right Arrow)
    arrow2 = ws.shapes.add(
        MsoDrawingType.RIGHT_ARROW,
        upper_left_row=2,
        upper_left_column=15,
        lower_right_row=4,
        lower_right_column=17
    )
    arrow2.name = "Arrow2"
    arrow2.text = "→"
    arrow2.fill.fill_type = FillType.SOLID
    arrow2.fill.fore_color = "D3D3D3"
    arrow2.line.is_visible = True
    arrow2.line.color = "696969"
    arrow2.line.weight = 9525
    arrow2.font.name = "Arial"
    arrow2.font.size = 16.0
    arrow2.text_horizontal_alignment = TextAlignmentType.CENTER
    arrow2.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {arrow2.name} (Right Arrow)")
    
    # Shape 5: Finance Approval (Rectangle) - Teal
    finance_shape = ws.shapes.add(
        MsoDrawingType.RECTANGLE,
        upper_left_row=1,
    