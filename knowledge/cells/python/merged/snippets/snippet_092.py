def test_create_workflow_with_shapes():
    """
    Create a new Excel file with dummy data and add workflow shapes.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("createshape")
    
    output_path = examples_output_path("createshape", "example_test_create_workflow.xlsx")
    
    # Create a new workbook
    print("Creating new workbook...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "Workflow"
    
    # Add dummy data for the workflow
    print("\nAdding dummy data...")
    # Add headers
    ws.cells["A1"].value = "Step"
    ws.cells["B1"].value = "Task Name"
    ws.cells["C1"].value = "Description"
    ws.cells["D1"].value = "Status"
    ws.cells["E1"].value = "Owner"
    
    # Add data rows
    dummy_data = [
        [1, "Start", "Begin the process", "Completed", "John"],
        [2, "Data Collection", "Gather required information", "In Progress", "Jane"],
        [3, "Analysis", "Analyze the collected data", "Pending", "Bob"],
        [4, "Decision", "Review and make decision", "Pending", "Alice"],
        [5, "Implementation", "Implement the solution", "Not Started", "Charlie"],
        [6, "Testing", "Test the implementation", "Not Started", "David"],
        [7, "Deployment", "Deploy to production", "Not Started", "Eve"],
        [8, "End", "Process complete", "Not Started", "Frank"],
    ]
    
    for row_idx, row_data in enumerate(dummy_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(dummy_data)} rows of data")
    
    # Add workflow shapes
    print("\nAdding workflow shapes...")
    
    # Shape 1: Start (Rounded Rectangle) - Green
    start_shape = ws.shapes.add(
        MsoDrawingType.ROUNDED_RECTANGLE,
        upper_left_row=1,
        upper_left_column=7,
        lower_right_row=4,
        lower_right_column=10
    )
    start_shape.name = "Start"
    start_shape.text = "START"
    start_shape.fill.fill_type = FillType.SOLID
    start_shape.fill.fore_color = "90EE90"  # Light green
    start_shape.line.is_visible = True
    start_shape.line.color = "006400"  # Dark green
    start_shape.line.weight = 12700  # 1 pt
    start_shape.font.name = "Arial"
    start_shape.font.size = 14.0
    start_shape.font.bold = True
    start_shape.font.color = "000000"
    start_shape.text_horizontal_alignment = TextAlignmentType.CENTER
    start_shape.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {start_shape.name} (Rounded Rectangle)")
    
    # Shape 2: Arrow 1 (Right Arrow) - Gray
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
    arrow1.fill.fore_color = "D3D3D3"  # Light gray
    arrow1.line.is_visible = True
    arrow1.line.color = "696969"  # Dim gray
    arrow1.line.weight = 9525  # 0.75 pt
    arrow1.font.name = "Arial"
    arrow1.font.size = 16.0
    arrow1.text_horizontal_alignment = TextAlignmentType.CENTER
    arrow1.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {arrow1.name} (Right Arrow)")
    
    # Shape 3: Process 1 (Rectangle) - Blue
    process1 = ws.shapes.add(
        MsoDrawingType.RECTANGLE,
        upper_left_row=1,
        upper_left_column=12,
        lower_right_row=4,
        lower_right_column=15
    )
    process1.name = "Process1"
    process1.text = "Data\nCollection"
    process1.fill.fill_type = FillType.SOLID
    process1.fill.fore_color = "87CEEB"  # Sky blue
    process1.line.is_visible = True
    process1.line.color = "00008B"  # Dark blue
    process1.line.weight = 12700  # 1 pt
    process1.font.name = "Arial"
    process1.font.size = 11.0
    process1.font.bold = True
    process1.text_horizontal_alignment = TextAlignmentType.CENTER
    process1.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {process1.name} (Rectangle)")
    
    # Shape 4: Arrow 2 (Right Arrow) - Gray
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
    arrow2.fill.fore_color = "D3D3D3"  # Light gray
    arrow2.line.is_visible = True
    arrow2.line.color = "696969"  # Dim gray
    arrow2.line.weight = 9525  # 0.75 pt
    arrow2.font.name = "Arial"
    arrow2.font.size = 16.0
    arrow2.text_horizontal_alignment = TextAlignmentType.CENTER
    arrow2.text_vertical_alignment = TextAnchorType.MIDDLE
    print(f"  Added: {arrow2.name} (