def test_create_surface_chart():
    """Create a surface chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data for surface chart (matrix)
    ws.cells["A1"].value = "X\\Y"
    ws.cells["B1"].value = 1
    ws.cells["C1"].value = 2
    ws.cells["D1"].value = 3
    ws.cells["E1"].value = 4
    
    ws.cells["A2"].value = 1
    ws.cells["A3"].value = 2
    ws.cells["A4"].value = 3
    ws.cells["A5"].value = 4
    
    # Create a surface function z = x^2 + y^2
    for i in range(2, 6):
        for j in range(2, 6):
            x = i - 1
            y = j - 1
            z = x**2 + y**2
            ws.cells[f"{chr(64+j)}{i}"].value = z
    
    # Create 3D surface chart
    chart = ws.charts.add_surface(0, 4, 20, 12, is_3d=True, wireframe=False)
    chart.title = "3D Surface Chart"
    chart.show_legend = True
    
    # Add series
    chart.n_series.add("B2:E5", category_data="A2:A5", name="Surface")
    
    # Save
    output_path = examples_output_path("progcharts", "example_surface_chart_3d.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")
    
    # Create wireframe surface chart
    wb2 = Workbook()
    ws2 = wb2.worksheets[0]
    
    # Copy data
    for i in range(1, 6):
        for j in range(1, 6):
            if i == 1 and j == 1:
                ws2.cells[f"{chr(64+j)}{i}"].value = "X\\Y"
            elif i == 1:
                ws2.cells[f"{chr(64+j)}{i}"].value = j - 1
            elif j == 1:
                ws2.cells[f"{chr(64+j)}{i}"].value = i - 1
            else:
                x = i - 1
                y = j - 1
                z = x**2 + y**2
                ws2.cells[f"{chr(64+j)}{i}"].value = z
    
    chart2 = ws2.charts.add_surface(0, 4, 20, 12, is_3d=True, wireframe=True)
    chart2.title = "3D Wireframe Surface Chart"
    
    chart2.n_series.add("B2:E5", category_data="A2:A5", name="Surface")
    
    output_path2 = examples_output_path("progcharts", "example_surface_chart_wireframe.xlsx")
    wb2.save(output_path2)
    assert os.path.exists(output_path2)
    print(f"Created: {output_path2}")