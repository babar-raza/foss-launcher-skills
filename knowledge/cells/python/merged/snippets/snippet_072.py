def test_create_bar_chart():
    """Create a bar (column) chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Product"
    ws.cells["B1"].value = "Q1"
    ws.cells["C1"].value = "Q2"
    ws.cells["D1"].value = "Q3"
    ws.cells["E1"].value = "Q4"
    
    products = ["Product A", "Product B", "Product C", "Product D"]
    data = [
        [120, 150, 180, 200],
        [90, 110, 130, 160],
        [200, 220, 190, 210],
        [150, 170, 160, 180]
    ]
    
    for i, product in enumerate(products, 2):
        ws.cells[f"A{i}"].value = product
        for j, value in enumerate(data[i-2], 2):
            ws.cells[f"{chr(64+j)}{i}"].value = value
    
    # Create bar chart
    chart = ws.charts.add_bar(0, 6, 20, 14)
    chart.title = "Quarterly Sales by Product"
    chart.category_data = "A2:A5"
    chart.bar_direction = "col"
    chart.grouping = "clustered"
    chart.gap_width = 150
    chart.show_legend = True
    
    # Add series
    chart.n_series.add("B2:B5", category_data="A2:A5", name="Q1")
    chart.n_series.add("C2:C5", category_data="A2:A5", name="Q2")
    chart.n_series.add("D2:D5", category_data="A2:A5", name="Q3")
    chart.n_series.add("E2:E5", category_data="A2:A5", name="Q4")
    
    # Save
    output_path = examples_output_path("progcharts", "example_bar_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")