def test_create_radar_chart():
    """Create radar charts from scratch."""
    # Test standard radar chart
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Metric"
    ws.cells["B1"].value = "Product A"
    ws.cells["C1"].value = "Product B"
    ws.cells["D1"].value = "Product C"
    
    metrics = ["Quality", "Price", "Service", "Features", "Reliability"]
    data = [
        [8, 6, 9],
        [7, 8, 6],
        [9, 7, 8],
        [6, 9, 7],
        [8, 8, 9]
    ]
    
    for i, metric in enumerate(metrics, 2):
        ws.cells[f"A{i}"].value = metric
        for j, value in enumerate(data[i-2], 2):
            ws.cells[f"{chr(64+j)}{i}"].value = value
    
    # Create standard radar chart
    chart = ws.charts.add_radar(0, 4, 20, 12, radar_style="standard")
    chart.title = "Product Comparison - Standard Radar"
    chart.category_data = "A2:A6"
    chart.show_legend = True
    
    chart.n_series.add("B2:B6", category_data="A2:A6", name="Product A")
    chart.n_series.add("C2:C6", category_data="A2:A6", name="Product B")
    chart.n_series.add("D2:D6", category_data="A2:A6", name="Product C")
    
    output_path = examples_output_path("progcharts", "example_radar_chart_standard.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")
    
    # Test filled radar chart
    wb2 = Workbook()
    ws2 = wb2.worksheets[0]
    
    # Copy data
    for i in range(1, 7):
        for j in range(1, 5):
            if i == 1 and j == 1:
                ws2.cells[f"{chr(64+j)}{i}"].value = "Metric"
            elif i == 1:
                ws2.cells[f"{chr(64+j)}{i}"].value = f"Product {chr(64+j)}"
            elif j == 1:
                ws2.cells[f"{chr(64+j)}{i}"].value = metrics[i-2]
            else:
                ws2.cells[f"{chr(64+j)}{i}"].value = data[i-2][j-2]
    
    chart2 = ws2.charts.add_radar(0, 4, 20, 12, radar_style="filled")
    chart2.title = "Product Comparison - Filled Radar"
    chart2.category_data = "A2:A6"
    chart2.show_legend = True
    
    chart2.n_series.add("B2:B6", category_data="A2:A6", name="Product A")
    chart2.n_series.add("C2:C6", category_data="A2:A6", name="Product B")
    chart2.n_series.add("D2:D6", category_data="A2:A6", name="Product C")
    
    output_path2 = examples_output_path("progcharts", "example_radar_chart_filled.xlsx")
    wb2.save(output_path2)
    assert os.path.exists(output_path2)
    print(f"Created: {output_path2}")