def test_create_scatter_chart():
    """Create a scatter (XY) chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "X"
    ws.cells["B1"].value = "Y1"
    ws.cells["C1"].value = "Y2"
    
    x_values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y1_values = [2, 4, 5, 4, 5, 7, 8, 9, 10, 12]
    y2_values = [1, 3, 2, 5, 4, 6, 5, 8, 7, 9]
    
    for i, (x, y1, y2) in enumerate(zip(x_values, y1_values, y2_values), 2):
        ws.cells[f"A{i}"].value = x
        ws.cells[f"B{i}"].value = y1
        ws.cells[f"C{i}"].value = y2
    
    # Create scatter chart
    chart = ws.charts.add_scatter(0, 4, 20, 12)
    chart.title = "Scatter Plot Example"
    chart.scatter_style = "lineMarker"
    chart.show_legend = True
    
    # Add series with x_values
    chart.n_series.add("B2:B11", category_data="A2:A11", name="Series 1", x_values="A2:A11")
    chart.n_series.add("C2:C11", category_data="A2:A11", name="Series 2", x_values="A2:A11")
    
    # Save
    output_path = examples_output_path("progcharts", "example_scatter_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")