def test_create_map_chart():
    """Create a map (region map) chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data - sales by region
    ws.cells["A1"].value = "Region"
    ws.cells["B1"].value = "Sales"
    
    regions = ["California", "Texas", "New York", "Florida", "Illinois", "Pennsylvania", "Ohio", "Georgia"]
    sales = [500000, 450000, 400000, 350000, 300000, 280000, 250000, 220000]
    
    for i, (region, sale) in enumerate(zip(regions, sales), 2):
        ws.cells[f"A{i}"].value = region
        ws.cells[f"B{i}"].value = sale
    
    # Create map chart
    chart = ws.charts.add_map(0, 4, 20, 12)
    chart.title = "Sales by Region"
    chart.show_legend = True
    
    # Add series
    chart.n_series.add("B2:B9", category_data="A2:A9", name="Sales")
    
    # Save
    output_path = examples_output_path("progcharts", "example_map_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")