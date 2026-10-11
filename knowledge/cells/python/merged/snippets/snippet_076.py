def test_create_waterfall_chart():
    """Create a waterfall chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Item"
    ws.cells["B1"].value = "Value"
    
    items = ["Starting", "Sales", "Costs", "Expenses", "Taxes", "Ending"]
    values = [1000, 500, -200, -150, -100, 1050]
    
    for i, (item, val) in enumerate(zip(items, values), 2):
        ws.cells[f"A{i}"].value = item
        ws.cells[f"B{i}"].value = val
    
    # Create waterfall chart
    chart = ws.charts.add_waterfall(0, 4, 20, 12)
    chart.title = "Cash Flow Waterfall"
    chart.category_data = "A2:A7"
    chart.show_legend = False
    
    # Add series
    chart.n_series.add("B2:B7", category_data="A2:A7", name="Cash Flow")
    
    # Save
    output_path = examples_output_path("progcharts", "example_waterfall_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")